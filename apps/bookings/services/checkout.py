"""
Concurrency Control and Checkout Service for WellTrip.
Enforces Non-Negotiable Concurrency and Stock Locking Requirements:
- Uses transaction.atomic() + select_for_update() on all constrained resources.
- Zero-Trust inventory checks: raises StockUnavailableError if any item is exhausted.
- 15-Minute TTL cancellation & auto-restoration worker.
"""
from datetime import datetime, date
from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.audit import record_audit_log
from apps.bookings.models import Booking, BookingItem, BookingStatus, BookingItemType
from apps.bookings.services.pricing import parse_date, parse_guests, room_option_title, stay_dates
from apps.accommodations.models import AccommodationStatus, Room, RoomPricingCalendar
from apps.core.pricing import customer_price
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot
from apps.otop.models import OTOPProduct
from django.utils.translation import gettext as _


class StockUnavailableError(Exception):
    """Raised when a room, wellness slot, or product is out of stock during checkout."""
    pass


def _fee_split(owner_unit_price, quantity, subtotal):
    owner_amount = owner_unit_price * quantity
    return {"owner_amount": owner_amount, "platform_fee": subtotal - owner_amount}


@transaction.atomic
def process_checkout(
    user,
    cart_items,
    customer_notes="",
    request=None,
    shipping_fee=Decimal("0.00"),
    discount_amount=Decimal("0.00"),
    coupon_code="",
    shipping_address=None,
):
    """
    Executes multi-vendor checkout with strict row-locking (select_for_update).
    Guarantees no race condition or negative inventory can ever occur.
    """
    if not cart_items:
        raise ValueError(_("ตะกร้าสินค้าว่างเปล่า ไม่สามารถดำเนินการสั่งซื้อได้"))

    total_booking_amount = Decimal("0.00")
    pending_items_to_create = []

    # Iterate and lock every resource first
    for item in cart_items:
        item_type = item.get("item_type")
        entity_id = item.get("entity_id")
        quantity = int(item.get("quantity", 1))

        if item_type == BookingItemType.ROOM:
            # Book room for specified date
            try:
                room = Room.objects.select_related("accommodation__owner").get(
                    id=entity_id, is_active=True, accommodation__status=AccommodationStatus.ACTIVE,
                )
            except (Room.DoesNotExist, ValueError, DjangoValidationError):
                raise StockUnavailableError(_("ไม่พบห้องพักที่เลือก หรือห้องพักนี้ปิดการจองแล้ว"))

            check_in = parse_date(item.get("date"))
            if check_in is None or check_in < timezone.localdate():
                # The cart can sit in the session overnight: never sell a night that has passed
                raise StockUnavailableError(_("วันเช็คอินของ '{name}' ผ่านมาแล้ว กรุณาลบออกแล้วเลือกวันใหม่").format(name=room.name))
            nights = max(1, int(item.get("nights", 1) or 1))
            options = room.cooling_options()
            cooling = item.get("cooling") if item.get("cooling") in options else options[0]
            guests = parse_guests(item.get("guests"), room)
            if isinstance(guests, str):
                raise StockUnavailableError(guests)
            units = guests if room.is_per_person else 1

            # Lock and decrement availability for every night of the stay
            for booking_date in stay_dates(check_in, nights):
                calendar = (
                    RoomPricingCalendar.objects.select_for_update()
                    .filter(room=room, date=booking_date)
                    .first()
                )

                # If no custom pricing exists, use room base price and total room capacity
                if not calendar:
                    calendar = RoomPricingCalendar.objects.create(
                        room=room,
                        date=booking_date,
                        price=room.base_price_per_night,
                        available_count=room.total_rooms_count,
                    )
                    calendar = RoomPricingCalendar.objects.select_for_update().get(id=calendar.id)

                if calendar.available_count < quantity:
                    raise StockUnavailableError(_("ห้องพัก '{name}' เต็มแล้วสำหรับวันที่ {booking_date}").format(name=room.name, booking_date=booking_date))

                calendar.available_count -= quantity
                calendar.save(update_fields=["available_count"])

                owner_nightly = room.owner_nightly_price(cooling, calendar.price)
                unit_price = customer_price(owner_nightly) * units
                subtotal = unit_price * quantity
                total_booking_amount += subtotal

                pending_items_to_create.append({
                    "vendor": room.accommodation.owner,
                    "item_type": BookingItemType.ROOM,
                    "entity_id": str(room.id),
                    "item_title_snapshot": room_option_title(room, cooling, guests),
                    "unit_price_snapshot": unit_price,
                    "quantity": quantity,
                    "subtotal": subtotal,
                    "owner_amount": owner_nightly * units * quantity,
                    "platform_fee": subtotal - owner_nightly * units * quantity,
                    "booking_metadata": {
                        "date": str(booking_date), "check_in": str(check_in), "nights": nights,
                        "cooling": cooling, "guests": guests, "pricing_mode": room.pricing_mode,
                        "accommodation_id": str(room.accommodation_id),
                    },
                })

        elif item_type == BookingItemType.WELLNESS:
            slot = None
            try:
                slot = (
                    WellnessTimeSlot.objects.select_for_update()
                    .select_related("service__owner")
                    .get(id=int(entity_id))
                )
            except (ValueError, TypeError, WellnessTimeSlot.DoesNotExist):
                slot = None

            if slot:
                if not slot.service.is_active or slot.date < timezone.localdate():
                    raise StockUnavailableError(_("รอบเวลาบริการ '{name}' ปิดรับจองแล้ว").format(name=slot.service.name))
                if slot.capacity_available < quantity:
                    raise StockUnavailableError(_("รอบเวลาบริการ '{name}' เต็มแล้ว").format(name=slot.service.name))

                slot.capacity_available -= quantity
                slot.save(update_fields=["capacity_available"])

                subtotal = slot.service.customer_price * quantity
                total_booking_amount += subtotal

                pending_items_to_create.append({
                    "vendor": slot.service.owner,
                    "item_type": BookingItemType.WELLNESS,
                    "entity_id": str(slot.id),
                    "item_title_snapshot": f"{slot.service.name} [{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}]",
                    "unit_price_snapshot": slot.service.customer_price,
                    "quantity": quantity,
                    "subtotal": subtotal,
                    **_fee_split(slot.service.price, quantity, subtotal),
                    "booking_metadata": {"date": str(slot.date), "slot_id": slot.id},
                })
            else:
                service = WellnessService.objects.select_related("owner").filter(id=entity_id, is_active=True).first()
                if service is None:
                    raise StockUnavailableError(_("บริการนี้ปิดรับจองแล้ว กรุณาลบออกจากตะกร้า"))
                subtotal = service.customer_price * quantity
                total_booking_amount += subtotal

                pending_items_to_create.append({
                    "vendor": service.owner,
                    "item_type": BookingItemType.WELLNESS,
                    "entity_id": str(service.id),
                    "item_title_snapshot": _("{name} ({duration_minutes} นาที)").format(name=service.name, duration_minutes=service.duration_minutes),
                    "unit_price_snapshot": service.customer_price,
                    "quantity": quantity,
                    "subtotal": subtotal,
                    **_fee_split(service.price, quantity, subtotal),
                    "booking_metadata": {"duration_minutes": service.duration_minutes},
                })

        elif item_type == BookingItemType.OTOP:
            product = (
                OTOPProduct.objects.select_for_update()
                .select_related("owner")
                .filter(id=entity_id, is_active=True)
                .first()
            )
            if product is None:
                raise StockUnavailableError(_("สินค้านี้ปิดการขายแล้ว กรุณาลบออกจากตะกร้า"))

            if product.stock_quantity < quantity:
                raise StockUnavailableError(_("สินค้า '{name}' คงเหลือไม่เพียงพอ (เหลือ {stock_quantity} ชิ้น)").format(name=product.name, stock_quantity=product.stock_quantity))

            product.stock_quantity -= quantity
            product.save(update_fields=["stock_quantity", "updated_at"])

            subtotal = product.customer_price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": product.owner,
                "item_type": BookingItemType.OTOP,
                "entity_id": str(product.id),
                "item_title_snapshot": product.name,
                "unit_price_snapshot": product.customer_price,
                "quantity": quantity,
                "subtotal": subtotal,
                **_fee_split(product.price, quantity, subtotal),
                "booking_metadata": {"category": product.category},
            })

        elif item_type == BookingItemType.FOOD:
            menu = FoodMenu.objects.select_related("owner").filter(id=entity_id, is_available=True).first()
            if menu is None:
                raise StockUnavailableError(_("เมนูนี้ปิดการขายแล้ว กรุณาลบออกจากตะกร้า"))
            subtotal = menu.customer_price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": menu.owner,
                "item_type": BookingItemType.FOOD,
                "entity_id": str(menu.id),
                "item_title_snapshot": menu.name,
                "unit_price_snapshot": menu.customer_price,
                "quantity": quantity,
                "subtotal": subtotal,
                **_fee_split(menu.price, quantity, subtotal),
                "booking_metadata": {"wellness_category": menu.wellness_category},
            })

    if coupon_code and discount_amount > 0:
        # Lock the coupon so two simultaneous checkouts cannot both take its last use
        from apps.community.models import Coupon
        coupon = Coupon.objects.select_for_update().filter(code=coupon_code).first()
        ok, msg = (False, _("ไม่พบคูปองส่วนลดนี้")) if coupon is None else coupon.is_valid_for(total_booking_amount)
        if ok:
            ok, msg = coupon.check_usage(user)
        if not ok:
            raise StockUnavailableError(msg)
        discount_amount = min(discount_amount, coupon.discount_amount, total_booking_amount)

    final_total = max(Decimal("0.00"), total_booking_amount + shipping_fee - discount_amount)

    # Create Booking
    booking = Booking.objects.create(
        customer=user,
        total_amount=final_total,
        shipping_fee=shipping_fee,
        discount_amount=discount_amount,
        coupon_code=coupon_code,
        shipping_address=shipping_address or {},
        customer_notes=customer_notes,
        status=BookingStatus.AWAITING_PAYMENT,
    )

    # Bulk create items
    for item_data in pending_items_to_create:
        BookingItem.objects.create(booking=booking, **item_data)

    record_audit_log(
        request=request,
        action="CREATE",
        model_name="Booking",
        object_id=str(booking.id),
        changes={
            "booking_code": booking.booking_code,
            "total_amount": str(booking.total_amount),
            "item_count": len(pending_items_to_create),
        },
        user=user,
    )

    return booking


def cancel_and_restore_expired_bookings():
    """
    Finds all bookings where payment countdown expired (15-min TTL)
    and restores inventories safely within a transaction.
    """
    now = timezone.now()
    # A slip uploaded in time is still waiting for a decision: keep its stock held
    expired_bookings = Booking.objects.filter(
        status=BookingStatus.AWAITING_PAYMENT,
        expires_at__lt=now,
    ).exclude(payment__slips__verification_status="PENDING_CHECK")

    restored_count = 0

    for booking in expired_bookings:
        with transaction.atomic():
            booking_locked = Booking.objects.select_for_update().get(id=booking.id)
            if booking_locked.status != BookingStatus.AWAITING_PAYMENT:
                continue

            # Restore each locked entity
            for item in booking_locked.items.all():
                if item.item_type == BookingItemType.ROOM:
                    date_str = item.booking_metadata.get("date")
                    if date_str:
                        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                        cal = (
                            RoomPricingCalendar.objects.select_for_update()
                            .filter(room_id=item.entity_id, date=booking_date)
                            .first()
                        )
                        if cal:
                            cal.available_count += item.quantity
                            cal.save(update_fields=["available_count"])

                elif item.item_type == BookingItemType.WELLNESS:
                    # Only slot bookings reserve capacity; plain service bookings store a UUID
                    slot_id = item.booking_metadata.get("slot_id")
                    slot = (
                        WellnessTimeSlot.objects.select_for_update().filter(id=slot_id).first()
                        if slot_id else None
                    )
                    if slot:
                        slot.capacity_available += item.quantity
                        slot.save(update_fields=["capacity_available"])

                elif item.item_type == BookingItemType.OTOP:
                    prod = (
                        OTOPProduct.objects.select_for_update()
                        .filter(id=item.entity_id)
                        .first()
                    )
                    if prod:
                        prod.stock_quantity += item.quantity
                        prod.save(update_fields=["stock_quantity", "updated_at"])

            booking_locked.status = BookingStatus.PAYMENT_EXPIRED
            booking_locked.save(update_fields=["status", "updated_at"])

            record_audit_log(
                action="UPDATE",
                model_name="Booking",
                object_id=str(booking_locked.id),
                changes={"status": BookingStatus.PAYMENT_EXPIRED, "reason": "TTL_15_MIN_EXPIRED"},
            )
            restored_count += 1

    return restored_count
