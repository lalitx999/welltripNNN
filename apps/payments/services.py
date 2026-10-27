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
from apps.core.services.notifications import (
    send_booking_voucher_and_order_alert,
    send_slip_rejected_alert,
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


def _json_safe(payload: dict) -> dict:
    """Sanitize Decimal and datetime objects for JSONField serialization."""
    return {str(k): str(v) for k, v in payload.items()}


def verify_slip_automatically(slip_id, *, provider_func=None) -> tuple[bool, PaymentSlip, str]:
    """
    Execute full slip verification workflow:
    1. Call EasySlip OCR provider (outside DB lock)
    2. Enforce financial rules & DB unique constraint in atomic transaction with select_for_update
    3. Update Payment and Booking status
    4. Dispatch transactional email alerts
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

        rejection_reason = _check_money_rules(payment, slip, amount, trans_ref, trans_at)
        slip.amount_seen = amount
        slip.provider_reference = trans_ref
        slip.checked_at = timezone.now()

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

    # 3. Dispatch transactional notifications (outside DB transaction)
    if is_verified:
        send_booking_voucher_and_order_alert(payment)
    else:
        send_slip_rejected_alert(payment, rejection_reason)

    return is_verified, slip, msg
