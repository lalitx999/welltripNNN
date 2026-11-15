"""
Automated Bank Slip Verification Service (EasySlip API v1 Integration).
Performs zero-trust OCR extraction, financial money-safety rule validation,
anti-fraud duplicate checks, atomic status transition, and transactional email dispatches.
"""
import io
import json
import logging
from decimal import Decimal
from datetime import timedelta
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.payments.models import (
    Payment,
    PaymentSlip,
    PaymentStatus,
    SlipVerificationStatus,
)

logger = logging.getLogger(__name__)


def _call_easyslip_provider(image_file) -> dict:
    """
    Dispatch slip image to EasySlip API v1 endpoint and parse bank transaction payload.
    Docs: https://document.easyslip.com/
    """
    api_key = getattr(settings, "EASYSLIP_API_KEY", "") or ""
    provider_url = getattr(
        settings,
        "EASYSLIP_URL",
        "https://developer.easyslip.com/api/v1/verify",
    )

    if not api_key:
        raise ValueError("ไม่ได้กำหนด EASYSLIP_API_KEY ในการตั้งค่าระบบ")

    if hasattr(image_file, "seek"):
        image_file.seek(0)
    image_bytes = image_file.read() if hasattr(image_file, "read") else image_file

    filename = getattr(image_file, "name", "slip.jpg") or "slip.jpg"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
    }
    is_v2 = "/v2/" in provider_url
    file_field = "image" if is_v2 else "file"
    files = {
        file_field: (filename, image_bytes, "image/jpeg"),
    }

    try:
        resp = requests.post(provider_url, headers=headers, files=files, timeout=20)
    except requests.RequestException as exc:
        logger.error("EasySlip API connection failed: %s", exc)
        raise ValueError(f"ไม่สามารถเชื่อมต่อไปยังเซิร์ฟเวอร์ EasySlip ได้: {str(exc)}") from exc

    try:
        res_json = resp.json()
    except Exception:
        raise ValueError(f"EasySlip ตอบกลับด้วยข้อมูลที่ไม่ใช่ JSON (HTTP {resp.status_code})")

    if resp.status_code != 200:
        err_msg = res_json.get("message") or res_json.get("error") or f"HTTP {resp.status_code}"
        raise ValueError(f"EasySlip ตรวจสอบสลิปไม่ผ่าน: {err_msg}")

    data = res_json.get("data", {})
    if not data:
        raise ValueError("EasySlip ไม่พบข้อมูลการโอนเงินในรูปภาพที่อัปโหลด")

    raw_slip = data.get("rawSlip") or data

    # Extract transfer amount
    amount_raw = data.get("amountInSlip")
    if amount_raw is None:
        amount_obj = raw_slip.get("amount", {})
        if isinstance(amount_obj, dict):
            amount_raw = amount_obj.get("amount") or 0
        else:
            amount_raw = amount_obj or 0

    try:
        amount = Decimal(str(amount_raw))
    except Exception as exc:
        raise ValueError(f"ไม่สามารถอ่านยอดเงินจากสลิปได้: {str(exc)}")

    # Extract transaction reference (transRef)
    trans_ref = str(raw_slip.get("transRef") or raw_slip.get("trans_ref") or "").strip()
    if not trans_ref:
        raise ValueError("ไม่พบรหัสอ้างอิงธุรกรรม (Transaction Reference) ในสลิป")

    # Extract transfer date/time
    date_str = raw_slip.get("date")
    trans_dt = timezone.now()
    if date_str:
        try:
            from datetime import datetime
            clean_date = date_str.replace("Z", "+00:00")
            trans_dt = datetime.fromisoformat(clean_date)
            if timezone.is_naive(trans_dt):
                trans_dt = timezone.make_aware(trans_dt, timezone.utc)
        except Exception:
            pass

    sender_info = raw_slip.get("sender", {})
    sender_name_obj = sender_info.get("account", {}).get("name", {}) or sender_info.get("name", {})
    if isinstance(sender_name_obj, dict):
        sender_name = sender_name_obj.get("th") or sender_name_obj.get("en") or ""
    else:
        sender_name = str(sender_name_obj or "")

    return {
        "amount": amount,
        "trans_ref": trans_ref,
        "trans_datetime": trans_dt,
        "sender_name": sender_name,
        "receiver": raw_slip.get("receiver", {}),
        "is_duplicate": data.get("isDuplicate", False),
        "raw_data": data,
        "provider": "EasySlip v2" if is_v2 else "EasySlip v1",
    }


def _check_money_rules(payment: Payment, slip: PaymentSlip, amount: Decimal, trans_ref: str, trans_at) -> str | None:
    """
    Enforces strict zero-trust financial safety rules.
    Returns None if valid, or a human-readable rejection reason.
    """
    if amount != payment.amount:
        return f"ยอดเงินในสลิปไม่ตรงกับยอดที่ต้องชำระ (ยอดที่ต้องชำระ: ฿{payment.amount:,.2f}, ยอดในสลิป: ฿{amount:,.2f})"

    if not trans_ref:
        return "ไม่พบรหัสอ้างอิงธุรกรรมธนาคารจากสลิป"

    # Anti-Duplicate Check
    duplicate = (
        PaymentSlip.objects.filter(
            provider_reference=trans_ref,
            verification_status=SlipVerificationStatus.VERIFIED,
        )
        .exclude(pk=slip.pk)
        .exists()
    )
    if duplicate:
        return f"สลิปนี้เคยถูกใช้ยืนยันการชำระเงินในระบบแล้ว (รหัสอ้างอิงซ้ำ: {trans_ref})"

    # Sanity check: Transfer timestamp should not predate payment by > 24 hours
    if trans_at is not None and payment.created_at is not None:
        if trans_at < (payment.created_at - timedelta(hours=24)):
            return "เวลาโอนเงินในสลิปเก่าเกินไป (โอนก่อนการสร้างคำสั่งซื้อเกิน 24 ชั่วโมง)"

    return None


def _digits_and_mask(value) -> str:
    """'xxx-x-x0448-x' -> 'xxxxx0448x'; keeps digits and mask letters, drops separators."""
    return "".join(ch for ch in str(value or "").lower() if ch.isdigit() or ch == "x")


def account_matches_payee(masked_account: str, payee_account: str) -> bool:
    """
    Banks mask most of the receiving account on a slip (e.g. 'xxx-x-x0448-x').
    It matches when every visible digit sits in the same place as in our account
    and enough digits are visible to mean something.
    """
    masked = _digits_and_mask(masked_account)
    payee = "".join(ch for ch in str(payee_account or "") if ch.isdigit())
    if not masked or len(masked) != len(payee):
        return False
    visible = [(i, ch) for i, ch in enumerate(masked) if ch.isdigit()]
    if len(visible) < 4:
        return False
    return all(payee[i] == ch for i, ch in visible)


def receiver_is_payee(receiver: dict) -> bool:
    """True when the slip's receiving account is the WellTrip payee account (or an accepted PromptPay proxy)."""
    if not isinstance(receiver, dict):
        return False
    account = receiver.get("account") or {}
    bank_account = (account.get("bank") or {}).get("account") or ""
    if bank_account and account_matches_payee(bank_account, settings.PAYEE_ACCOUNT_NUMBER):
        return True
    proxy_account = (account.get("proxy") or {}).get("account") or ""
    accepted = [p for p in (settings.PAYEE_PROXY_ACCOUNTS or []) if p]
    return bool(proxy_account) and any(account_matches_payee(proxy_account, p) for p in accepted)


def _send_to_manual_review(slip: PaymentSlip, reason: str, payload: dict) -> PaymentSlip:
    """Auto-check cannot decide: keep the slip PENDING_CHECK for an admin, with the reason."""
    slip.verification_notes = f"{reason} (ส่งต่อให้แอดมินตรวจ)"
    slip.provider_response_log = {"provider": _json_safe(payload), "manual_review_reason": reason}
    slip.save(update_fields=["amount_seen", "provider_reference", "verification_notes", "provider_response_log"])
    return slip


def _json_safe(payload: dict) -> dict:
    """Sanitize Decimal and datetime objects for JSONField serialization."""
    return {str(k): str(v) for k, v in payload.items()}


def verify_slip_automatically(slip_id, *, provider_func=None) -> tuple[bool, PaymentSlip, str]:
    """
    Execute full slip verification workflow:
    1. Call EasySlip OCR provider (outside DB lock)
    2. Enforce financial rules & DB unique constraint in atomic transaction with select_for_update
    3. Update Payment and Booking status
    4. Queue transactional email alerts
    """
    provider = provider_func or _call_easyslip_provider

    slip = PaymentSlip.objects.select_related("payment__booking__customer").filter(pk=slip_id).first()
    if not slip:
        raise ValueError(f"ไม่พบข้อมูลสลิป ID: {slip_id}")

    # 1. OCR Round-trip
    try:
        payload = provider(slip.image)
    except Exception as exc:
        logger.warning("Automated slip extraction failed for slip %s: %s", slip_id, exc)
        slip.verification_notes = f"ตรวจสอบอัตโนมัติไม่สำเร็จ: {str(exc)} (ส่งต่อให้แอดมินตรวจมือ)"
        slip.save(update_fields=["verification_notes"])
        return False, slip, str(exc)

    amount = Decimal(str(payload["amount"]))
    trans_ref = str(payload.get("trans_ref") or "").strip()
    trans_at = payload.get("trans_datetime")

    # 2. Atomic Transition under Database Concurrency Lock
    with transaction.atomic():
        booking = (
            Booking.objects.select_for_update()
            .filter(pk=slip.payment.booking_id)
            .first()
        )
        payment = (
            Payment.objects.select_for_update()
            .filter(pk=slip.payment_id)
            .first()
        )
        slip = PaymentSlip.objects.select_for_update().get(pk=slip.pk)

        if not payment or not booking:
            raise ValueError("ไม่พบข้อมูลการจองหรือข้อมูลการชำระเงิน")

        if slip.verification_status != SlipVerificationStatus.PENDING_CHECK:
            # An admin already decided while the provider call was running
            return slip.verification_status == SlipVerificationStatus.VERIFIED, slip, "already decided"

        slip.amount_seen = amount
        slip.provider_reference = trans_ref
        review_reason = None
        if booking.status != BookingStatus.AWAITING_PAYMENT:
            review_reason = f"การจองอยู่ในสถานะ {booking.get_status_display()} ไม่ใช่รอชำระเงิน"
        elif not receiver_is_payee(payload.get("receiver")):
            review_reason = "บัญชีผู้รับในสลิปไม่ตรงกับบัญชีรับเงินของ WellTrip"
        if review_reason:
            _send_to_manual_review(slip, review_reason, payload)
            return False, slip, review_reason

        rejection_reason = _check_money_rules(payment, slip, amount, trans_ref, trans_at)
        if rejection_reason is None and payload.get("is_duplicate"):
            # Not reused here, but EasySlip has seen it before: let a person look
            reason = "EasySlip แจ้งว่าสลิปนี้เคยถูกตรวจมาก่อน"
            _send_to_manual_review(slip, reason, payload)
            return False, slip, reason

        if rejection_reason is None:
            slip.verification_status = SlipVerificationStatus.VERIFIED
            slip.verification_notes = f"EasySlip ตรวจสอบอัตโนมัติสำเร็จ (Ref: {trans_ref})"
            slip.verified_at = timezone.now()
            slip.provider_response_log = {"provider": _json_safe(payload)}
            slip.save(
                update_fields=[
                    "verification_status",
                    "provider_reference",
                    "amount_seen",
                    "verification_notes",
                    "verified_at",
                    "provider_response_log",
                ]
            )

            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = trans_at or timezone.now()
            payment.save(update_fields=["status", "paid_at", "updated_at"])

            booking.status = BookingStatus.CONFIRMED
            booking.save(update_fields=["status", "updated_at"])
            is_verified = True
            msg = "สลิปถูกต้อง ยืนยันการชำระเงินสำเร็จ"
        else:
            slip.verification_status = SlipVerificationStatus.REJECTED
            slip.verification_notes = rejection_reason
            slip.provider_response_log = {
                "provider": _json_safe(payload),
                "reject_reason": rejection_reason,
            }
            slip.save(
                update_fields=[
                    "verification_status",
                    "provider_reference",
                    "amount_seen",
                    "verification_notes",
                    "provider_response_log",
                ]
            )
            is_verified = False
            msg = rejection_reason

    # 3. Queue notification emails (separate tasks so SMTP never delays this one)
    from apps.core.tasks import send_booking_voucher_task, send_slip_rejected_task

    if is_verified:
        send_booking_voucher_task.delay_on_commit(payment.id)
    else:
        send_slip_rejected_task.delay_on_commit(payment.id, rejection_reason)

    return is_verified, slip, msg


def review_slip(request, payment_id, action: str, notes: str = "") -> tuple[bool, str]:
    """
    Admin approves or rejects the pending slip of a payment.
    Locks booking, payment and slip so it cannot race the auto-check worker,
    and refuses to confirm a booking whose stock was already released.
    """
    from django.db import IntegrityError
    from django.utils.translation import gettext as _
    from apps.accounts.services.audit import record_audit_log
    from apps.core.tasks import send_booking_voucher_task, send_slip_rejected_task

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
        if not payment:
            return False, _("ไม่พบรายการชำระเงิน")
        booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
        slip = (
            PaymentSlip.objects.select_for_update()
            .filter(payment=payment, verification_status=SlipVerificationStatus.PENDING_CHECK)
            .order_by("-uploaded_at")
            .first()
        )
        if not slip:
            return False, _("ไม่มีสลิปที่รอตรวจสอบ (อาจถูกตรวจไปแล้ว)")

        slip.verified_by = request.user
        slip.verified_at = timezone.now()
        slip.verification_notes = notes

        if action == "APPROVE":
            if booking.status != BookingStatus.AWAITING_PAYMENT:
                return False, _(
                    "อนุมัติไม่ได้: การจอง {code} อยู่ในสถานะ '{status}' สต็อกอาจถูกคืนไปแล้ว กรุณาติดต่อลูกค้าเพื่อจองใหม่หรือคืนเงิน"
                ).format(code=booking.booking_code, status=booking.get_status_display())
            slip.verification_status = SlipVerificationStatus.VERIFIED
            try:
                with transaction.atomic():
                    slip.save()
            except IntegrityError:
                return False, _("อนุมัติไม่ได้: เลขอ้างอิงสลิป {ref} ถูกใช้ยืนยันการชำระเงินอื่นไปแล้ว").format(ref=slip.provider_reference)
            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = payment.paid_at or timezone.now()
            payment.save(update_fields=["status", "paid_at", "updated_at"])
            booking.status = BookingStatus.CONFIRMED
            booking.save(update_fields=["status", "updated_at"])
            send_booking_voucher_task.delay_on_commit(payment.id)
            audit_action, message = "PAYMENT_APPROVED", _("อนุมัติการชำระเงินสำหรับรหัส {booking_code} สำเร็จ")
        else:
            slip.verification_status = SlipVerificationStatus.REJECTED
            slip.save()
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=["status", "updated_at"])
            send_slip_rejected_task.delay_on_commit(payment.id, notes or _("สลิปไม่ผ่านการตรวจสอบ"))
            audit_action, message = "PAYMENT_REJECTED", _("ปฏิเสธสลิปการโอนเงิน รหัส {booking_code}")

        record_audit_log(
            request=request,
            action="UPDATE",
            model_name="Payment",
            object_id=str(payment.id),
            changes={
                "action": audit_action,
                "booking_code": booking.booking_code,
                "slip_ref": slip.provider_reference,
                "reason": notes,
            },
            user=request.user,
        )
    return True, message.format(booking_code=booking.booking_code)
