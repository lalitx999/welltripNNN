"""
Deposit bookings for homestays.

A guest may pay a deposit (DEPOSIT_PERCENT of the total, whole baht) instead of
the full amount when every line in the order is a house from one homestay. The
slip then covers only the deposit; the room nights are held from checkout and
stay locked to the guest once the deposit slip is confirmed (status CONFIRMED).
The homestay owner or an admin later records that the rest was paid on site
(status COMPLETED), or cancels the booking, which puts the nights back on sale.

A deposit not transferred in time is cancelled by the same 15-minute expiry job
as any other unpaid order (bookings.tasks.expire_unpaid_bookings_task).
"""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import UserRoles
from apps.accounts.services.audit import record_audit_log
from apps.core.pricing import round_baht


def deposit_percent() -> int:
    return int(getattr(settings, "DEPOSIT_PERCENT", 30))


def split_deposit(total):
    """(deposit, balance) for an order total: deposit rounded to whole baht, half up."""
    total = Decimal(str(total))
    deposit = min(total, round_baht(total * Decimal(deposit_percent()) / Decimal("100")))
    return deposit, total - deposit


def deposit_accommodation_id(lines):
    """
    The homestay id when every line is a house of that one homestay, else None.
    Each line is a dict with item_type and accommodation_id.
    """
    from apps.bookings.models import BookingItemType

    ids = {str(line.get("accommodation_id") or "") for line in lines}
    if not lines or any(line.get("item_type") != BookingItemType.ROOM for line in lines):
        return None
    if len(ids) != 1 or "" in ids:
        return None
    return ids.pop()


def cart_deposit_option(cart):
    """Deposit amounts to offer on the review page, or None when the cart cannot use a deposit."""
    from apps.accommodations.models import Room
    from apps.bookings.models import BookingItemType

    room_ids = [item.get("entity_id") for item in cart if str(item.get("item_type")).upper() == BookingItemType.ROOM]
    if not cart or len(room_ids) != len(cart):
        return None
    homes = dict(Room.objects.filter(id__in=room_ids).values_list("id", "accommodation_id"))
    lines = [{"item_type": BookingItemType.ROOM, "accommodation_id": homes.get(_uuid(rid))} for rid in room_ids]
    if deposit_accommodation_id(lines) is None:
        return None
    return {"percent": deposit_percent()}


def _uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def can_manage_stay_booking(user, booking) -> bool:
    """Admins, or the homestay owner who owns every line of a deposit booking."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role in (UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN):
        return True
    if user.role != UserRoles.HOMESTAY_OWNER:
        return False
    vendors = set(booking.items.values_list("vendor_id", flat=True))
    return vendors == {user.id}


def mark_balance_paid(request, booking_id):
    """Owner/admin confirms the guest paid the rest on site: the booking is completed."""
    from apps.bookings.models import Booking, BookingStatus

    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
        if booking is None or not can_manage_stay_booking(request.user, booking):
            return False, _("ไม่พบการจองนี้")
        if not booking.awaiting_balance:
            return False, _("การจอง {code} ไม่มียอดค้างชำระที่ต้องรับ").format(code=booking.booking_code)
        booking.balance_paid_at = timezone.now()
        booking.balance_received_by = request.user
        booking.status = BookingStatus.COMPLETED
        booking.save(update_fields=["balance_paid_at", "balance_received_by", "status", "updated_at"])
        record_audit_log(
            request=request, action="UPDATE", model_name="Booking", object_id=str(booking.id),
            changes={"action": "BALANCE_PAID", "booking_code": booking.booking_code, "balance_due": str(booking.balance_due)},
            user=request.user,
        )
    return True, _("บันทึกว่าได้รับเงินส่วนที่เหลือ ฿{amount} ของ {code} แล้ว").format(
        amount=f"{booking.balance_due:,.0f}", code=booking.booking_code,
    )


def cancel_booking(request, booking_id, reason):
    """Owner/admin cancels a stay booking that is not completed; held nights go back on sale."""
    from apps.bookings.models import Booking, BookingStatus
    from apps.bookings.services.checkout import restore_booking_stock
    from apps.payments.models import Payment, PaymentStatus

    reason = (reason or "").strip()
    if not reason:
        return False, _("กรุณาระบุเหตุผลที่ยกเลิก")
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
        if booking is None or not can_manage_stay_booking(request.user, booking):
            return False, _("ไม่พบการจองนี้")
        if booking.status not in (BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED):
            return False, _("การจอง {code} อยู่ในสถานะ '{status}' ยกเลิกไม่ได้").format(
                code=booking.booking_code, status=booking.get_status_display(),
            )
        restore_booking_stock(booking)
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancel_reason = reason[:255]
        booking.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
        Payment.objects.filter(booking=booking, status=PaymentStatus.PENDING).update(status=PaymentStatus.FAILED)
        record_audit_log(
            request=request, action="UPDATE", model_name="Booking", object_id=str(booking.id),
            changes={"action": "CANCELLED", "booking_code": booking.booking_code, "reason": booking.cancel_reason},
            user=request.user,
        )
    return True, _("ยกเลิกการจอง {code} และคืนห้องให้จองได้แล้ว").format(code=booking.booking_code)
