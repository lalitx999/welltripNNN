"""Partners mark paid OTOP items as shipped or delivered."""
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.permissions import scope_to_owner
from apps.accounts.services.audit import record_audit_log
from apps.bookings.models import BookingItem, BookingItemType, BookingStatus, FulfillmentStatus


def update_fulfillment(request, item_id, new_status, tracking_number=""):
    """Returns (ok, message). Only paid OTOP lines of this vendor (or any, for admins)."""
    if new_status not in (FulfillmentStatus.SHIPPED, FulfillmentStatus.DELIVERED):
        return False, _("สถานะการจัดส่งไม่ถูกต้อง")
    with transaction.atomic():
        item = (
            scope_to_owner(BookingItem.objects.select_for_update().select_related("booking"), request.user, "vendor")
            .filter(pk=item_id)
            .first()
        )
        if item is None:
            return False, _("ไม่พบรายการสินค้านี้")
        if item.item_type != BookingItemType.OTOP:
            return False, _("อัปเดตการจัดส่งได้เฉพาะสินค้า OTOP")
        if item.booking.status not in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED):
            return False, _("คำสั่งซื้อนี้ยังไม่ได้ชำระเงิน จึงยังไม่ควรจัดส่ง")
        if new_status == FulfillmentStatus.SHIPPED and not tracking_number.strip():
            return False, _("กรุณากรอกเลขพัสดุ")

        item.fulfillment_status = new_status
        fields = ["fulfillment_status"]
        if new_status == FulfillmentStatus.SHIPPED:
            item.tracking_number = tracking_number.strip()[:60]
            item.shipped_at = timezone.now()
            fields += ["tracking_number", "shipped_at"]
        item.save(update_fields=fields)
        record_audit_log(
            request=request, action="UPDATE", model_name="BookingItem", object_id=str(item.id),
            changes={"fulfillment_status": new_status, "tracking_number": item.tracking_number,
                     "booking_code": item.booking.booking_code},
        )
    return True, _("อัปเดตการจัดส่ง {code} เป็น '{status}' แล้ว").format(
        code=item.booking.booking_code, status=item.get_fulfillment_status_display()
    )
