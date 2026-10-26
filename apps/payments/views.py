from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required, can_view_object
from apps.accounts.services.audit import record_audit_log
from apps.bookings.models import Booking, BookingStatus
from apps.payments.models import Payment, PaymentSlip, PaymentStatus, SlipVerificationStatus
from apps.payments.forms import SlipUploadForm


@login_required
@require_http_methods(["GET", "POST"])
def payment_instruction_view(request, booking_id):
    """
    Tourist Payment Instruction View:
    1. Shows community KBANK receiving account and PromptPay QR data.
    2. Enforces ownership check (Anti-IDOR): only booking owner can pay.
    3. Handles bank slip upload with sanitization and validation.
    """
    booking = get_object_or_404(Booking, id=booking_id)

    # Anti-IDOR Ownership check
    if not can_view_object(request.user, booking):
        messages.error(request, "คุณไม่มีสิทธิ์เข้าถึงหน้านี้")
        return redirect('bookings:my_bookings')

    if booking.status == BookingStatus.PAYMENT_EXPIRED:
        messages.warning(request, "คำสั่งซื้อนี้หมดเวลาชำระเงิน 15 นาทีแล้ว ระบบได้ทำการปลดสต็อกคืนชุมชน")
        return redirect('bookings:detail', booking_id=booking.id)

    # Get or create payment record
    payment, created = Payment.objects.get_or_create(
        booking=booking,
        defaults={'amount': booking.total_amount}
    )

    if request.method == "POST":
        form = SlipUploadForm(request.POST, request.FILES)
        if form.is_valid():
            slip = form.save(commit=False)
            slip.payment = payment
            slip.verification_status = SlipVerificationStatus.PENDING_CHECK
            slip.save()

            payment.status = PaymentStatus.PENDING
            payment.save(update_fields=['status', 'updated_at'])

            record_audit_log(
                request=request,
                action="CREATE",
                model_name="PaymentSlip",
                object_id=str(slip.id),
                changes={
                    "booking_code": booking.booking_code,
                    "amount": str(payment.amount),
                    "provider_reference": slip.provider_reference,
                },
                user=request.user,
            )

            messages.success(request, "แนบสลิปเรียบร้อยแล้ว เจ้าหน้าที่ชุมชนจะทำการตรวจสอบและยืนยันการจอง")
            return redirect('bookings:detail', booking_id=booking.id)
        else:
            messages.error(request, "สลิปที่อัปโหลดไม่ถูกต้อง กรุณาตรวจสอบรูปภาพและรหัสอ้างอิง")
    else:
        form = SlipUploadForm()

    slips = payment.slips.order_by('-uploaded_at')

    return render(request, 'payments/instruction.html', {
        'booking': booking,
        'payment': payment,
        'form': form,
        'slips': slips,
        'remaining_seconds': booking.remaining_seconds,
    })


# ==============================================================================
# ADMIN OPERATIONS: SLIP CHECK & PAYMENT APPROVAL
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_payments_list_view(request):
    """Admin center view listing pending payments awaiting slip checks."""
    payments = Payment.objects.filter(
        status=PaymentStatus.PENDING
    ).select_related('booking__customer').order_by('-created_at')

    return render(request, 'payments/admin_list.html', {
        'payments': payments,
    })


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["GET", "POST"])
def admin_payment_review_view(request, payment_id):
    """
    Admin verification view: inspects bank slip image, verifies against bank records,
    and approves or rejects the payment.
    """
    payment = get_object_or_404(Payment.objects.select_related('booking__customer'), id=payment_id)
    latest_slip = payment.slips.filter(verification_status=SlipVerificationStatus.PENDING_CHECK).first()

    if request.method == "POST":
        action = request.POST.get('action')
        notes = request.POST.get('verification_notes', '').strip()

        if action == "APPROVE" and latest_slip:
            latest_slip.verification_status = SlipVerificationStatus.VERIFIED
            latest_slip.verified_by = request.user
            latest_slip.verified_at = timezone.now()
            latest_slip.verification_notes = notes
            latest_slip.save()

            payment.status = PaymentStatus.SUCCESS
            payment.save(update_fields=['status', 'updated_at'])

            booking = payment.booking
            booking.status = BookingStatus.CONFIRMED
            booking.save(update_fields=['status', 'updated_at'])

            record_audit_log(
                request=request,
                action="UPDATE",
                model_name="Payment",
                object_id=str(payment.id),
                changes={
                    "action": "PAYMENT_APPROVED",
                    "booking_code": booking.booking_code,
                    "slip_ref": latest_slip.provider_reference,
                },
                user=request.user,
            )

            messages.success(request, f"อนุมัติการชำระเงินสำหรับรหัส {booking.booking_code} สำเร็จ")
            return redirect('payments:admin_list')

        elif action == "REJECT" and latest_slip:
            latest_slip.verification_status = SlipVerificationStatus.REJECTED
            latest_slip.verified_by = request.user
            latest_slip.verified_at = timezone.now()
            latest_slip.verification_notes = notes
            latest_slip.save()

            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=['status', 'updated_at'])

            record_audit_log(
                request=request,
                action="UPDATE",
                model_name="Payment",
                object_id=str(payment.id),
                changes={
                    "action": "PAYMENT_REJECTED",
                    "reason": notes,
                },
                user=request.user,
            )

            messages.warning(request, f"ปฏิเสธสลิปการโอนเงิน รหัส {payment.booking.booking_code}")
            return redirect('payments:admin_list')

    return render(request, 'payments/admin_review.html', {
        'payment': payment,
        'slip': latest_slip,
    })
