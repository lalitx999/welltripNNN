"""
Stay bookings for homestay owners and admins: confirm deposit slips, record the
balance paid on site, and cancel bookings (nights go back on sale).
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.bookings.models import Booking, BookingItem, BookingItemType, BookingStatus
from apps.bookings.services.deposit import can_manage_stay_booking, cancel_booking, mark_balance_paid
from apps.payments.models import PaymentSlip, SlipVerificationStatus

STAY_ROLES = (UserRoles.HOMESTAY_OWNER, UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
TABS = ("action", "awaiting_balance", "all")


def _is_admin(user):
    return user.is_superuser or user.role in (UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN)


def stay_bookings_for(user, tab):
    room_lines = BookingItem.objects.filter(booking=OuterRef("pk"), item_type=BookingItemType.ROOM)
    if not _is_admin(user):
        room_lines = room_lines.filter(vendor=user)
    pending_slip = PaymentSlip.objects.filter(
        payment__booking=OuterRef("pk"), verification_status=SlipVerificationStatus.PENDING_CHECK,
    )
    qs = (
        Booking.objects.annotate(has_rooms=Exists(room_lines), slip_waiting=Exists(pending_slip))
        .filter(has_rooms=True)
        .select_related("customer", "payment")
        .prefetch_related("items", "payment__slips")
        .order_by("-created_at")
    )
    if tab == "action":
        qs = qs.filter(Q(slip_waiting=True, status=BookingStatus.AWAITING_PAYMENT) | Q(
            payment_plan="DEPOSIT", status=BookingStatus.CONFIRMED, balance_paid_at__isnull=True,
        ))
    elif tab == "awaiting_balance":
        qs = qs.filter(payment_plan="DEPOSIT", status=BookingStatus.CONFIRMED, balance_paid_at__isnull=True)
    return qs


@role_required(*STAY_ROLES)
def stay_bookings_view(request):
    tab = request.GET.get("tab", "action")
    if tab not in TABS:
        tab = "action"
    page = Paginator(stay_bookings_for(request.user, tab), 20).get_page(request.GET.get("page"))
    for booking in page:
        booking.can_manage = can_manage_stay_booking(request.user, booking)
        payment = getattr(booking, "payment", None) if hasattr(booking, "payment") else None
        slips = payment.slips.all() if payment else []
        booking.pending_slip = next((s for s in slips if s.verification_status == SlipVerificationStatus.PENDING_CHECK), None)
        booking.room_lines = [i for i in booking.items.all() if i.item_type == BookingItemType.ROOM]
    return render(request, "bookings/stay_bookings.html", {
        "tab": tab,
        "page_obj": page,
        "is_admin": _is_admin(request.user),
        "page_title": _("การจองที่พัก"),
    })


def _back(request):
    return redirect(f"/bookings/stays/?tab={request.POST.get('tab', 'action')}")


@role_required(*STAY_ROLES)
@require_POST
def stay_slip_review_view(request, booking_id):
    """Approve or reject the waiting slip (the deposit, or the full amount for admins)."""
    from apps.payments.services import review_slip

    booking = get_object_or_404(Booking.objects.select_related("payment"), id=booking_id)
    if not can_manage_stay_booking(request.user, booking) or not hasattr(booking, "payment"):
        messages.error(request, _("ไม่พบการจองนี้"))
        return _back(request)
    if not _is_admin(request.user) and not booking.is_deposit:
        # Owners confirm deposits; full payments are checked by the platform team
        messages.error(request, _("สลิปชำระเต็มจำนวนตรวจโดยทีมงาน WellTrip"))
        return _back(request)
    action = request.POST.get("action")
    if action not in ("APPROVE", "REJECT"):
        messages.error(request, _("คำสั่งไม่ถูกต้อง"))
        return _back(request)
    ok, message = review_slip(request, booking.payment.id, action, request.POST.get("notes", "").strip())
    (messages.success if ok else messages.error)(request, message)
    return _back(request)


@role_required(*STAY_ROLES)
@require_POST
def stay_balance_paid_view(request, booking_id):
    ok, message = mark_balance_paid(request, booking_id)
    (messages.success if ok else messages.error)(request, message)
    return _back(request)


@role_required(*STAY_ROLES)
@require_POST
def stay_cancel_view(request, booking_id):
    ok, message = cancel_booking(request, booking_id, request.POST.get("reason", ""))
    (messages.success if ok else messages.error)(request, message)
    return _back(request)
