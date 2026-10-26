"""
Concurrency Control and Checkout Service for WellTrip.
Enforces Non-Negotiable Concurrency and Stock Locking Requirements:
- Uses transaction.atomic() + select_for_update() on all constrained resources.
- Zero-Trust inventory checks: raises StockUnavailableError if any item is exhausted.
- 15-Minute TTL cancellation & auto-restoration worker.
"""
from datetime import datetime, date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.audit import record_audit_log
from apps.bookings.models import Booking, BookingItem, BookingStatus, BookingItemType
from apps.accommodations.models import Room, RoomPricingCalendar
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot
from apps.otop.models import OTOPProduct


class StockUnavailableError(Exception):
    """Raised when a room, wellness slot, or product is out of stock during checkout."""
    pass


@transaction.atomic
def process_checkout(user, cart_items, customer_notes="", request=None):
    """
    Executes multi-vendor checkout with strict row-locking (select_for_update).
    Guarantees no race condition or negative inventory can ever occur.
    """
    if not cart_items:
        raise ValueError("ตะกร้าสินค้าว่างเปล่า ไม่สามารถดำเนินการสั่งซื้อได้")

    total_booking_amount = Decimal("0.00")
    pending_items_to_create = []

    # Iterate and lock every resource first
    for item in cart_items:
        item_type = item.get("item_type")
        entity_id = item.get("entity_id")
        quantity = int(item.get("quantity", 1))

        if item_type == BookingItemType.ROOM:
            # Book room for specified date
            room = Room.objects.select_related("accommodation__owner").get(id=entity_id)
            booking_date_str = item.get("date")
            booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date() if isinstance(booking_date_str, str) else booking_date_str

            # Row lock the calendar row for this date
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
                # Re-query with lock
                calendar = RoomPricingCalendar.objects.select_for_update().get(id=calendar.id)

            if calendar.available_count < quantity:
                raise StockUnavailableError(f"ห้องพัก '{room.name}' เต็มแล้วสำหรับวันที่ {booking_date}")

            calendar.available_count -= quantity
            calendar.save(update_fields=["available_count"])

            subtotal = calendar.price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": room.accommodation.owner,
                "item_type": BookingItemType.ROOM,
                "entity_id": str(room.id),
                "item_title_snapshot": f"{room.name} ({room.accommodation.name})",
                "unit_price_snapshot": calendar.price,
                "quantity": quantity,
                "subtotal": subtotal,
                "booking_metadata": {"date": str(booking_date)},
            })

        elif item_type == BookingItemType.WELLNESS:
            slot = (
                WellnessTimeSlot.objects.select_for_update()
                .select_related("service__owner")
                .get(id=int(entity_id))
            )

            if slot.capacity_available < quantity:
                raise StockUnavailableError(f"รอบเวลาบริการ '{slot.service.name}' เต็มแล้ว")

            slot.capacity_available -= quantity
            slot.save(update_fields=["capacity_available"])

            subtotal = slot.service.price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": slot.service.owner,
                "item_type": BookingItemType.WELLNESS,
                "entity_id": str(slot.id),
                "item_title_snapshot": f"{slot.service.name} [{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}]",
                "unit_price_snapshot": slot.service.price,
                "quantity": quantity,
                "subtotal": subtotal,
                "booking_metadata": {"date": str(slot.date), "slot_id": slot.id},
            })

        elif item_type == BookingItemType.OTOP:
            product = (
                OTOPProduct.objects.select_for_update()
                .select_related("owner")
                .get(id=entity_id)
            )

            if product.stock_quantity < quantity:
                raise StockUnavailableError(f"สินค้า '{product.name}' คงเหลือไม่เพียงพอ (เหลือ {product.stock_quantity} ชิ้น)")

            product.stock_quantity -= quantity
            product.save(update_fields=["stock_quantity", "updated_at"])

            subtotal = product.price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": product.owner,
                "item_type": BookingItemType.OTOP,
                "entity_id": str(product.id),
                "item_title_snapshot": product.name,
                "unit_price_snapshot": product.price,
                "quantity": quantity,
                "subtotal": subtotal,
                "booking_metadata": {"category": product.category},
            })

        elif item_type == BookingItemType.FOOD:
            menu = FoodMenu.objects.select_related("owner").get(id=entity_id)
            subtotal = menu.price * quantity
            total_booking_amount += subtotal

            pending_items_to_create.append({
                "vendor": menu.owner,
                "item_type": BookingItemType.FOOD,
                "entity_id": str(menu.id),
                "item_title_snapshot": menu.name,
                "unit_price_snapshot": menu.price,
                "quantity": quantity,
                "subtotal": subtotal,
                "booking_metadata": {"wellness_category": menu.wellness_category},
            })

    # Create Booking
    booking = Booking.objects.create(
        customer=user,
        total_amount=total_booking_amount,
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
    expired_bookings = Booking.objects.filter(
        status=BookingStatus.AWAITING_PAYMENT,
        expires_at__lt=now,
    )

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
                    slot = (
                        WellnessTimeSlot.objects.select_for_update()
                        .filter(id=int(item.entity_id))
                        .first()
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
