"""
Centralized Notification Service (Hostinger SMTP Suite).
Provides robust, formatted, and audited email dispatches for:
1. Email OTP Verification (with 60-second cooldown rate limit & 10-minute expiry)
2. Admin New Merchant KYC Alert
3. Merchant KYC Decision Notification (Approval/Rejection)
4. Payment Confirmed & Digital Voucher Dispatches
5. Payment Slip Rejected Alert
"""
import logging
import secrets
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from apps.accounts.models import EmailVerificationOTP

logger = logging.getLogger(__name__)


def _site_url() -> str:
    return settings.SITE_URL.rstrip("/")


def _queue_mail(subject: str, message: str, recipient: str) -> bool:
    """
    Hand the email to the Celery worker, which retries on SMTP errors.
    One task per recipient, so a retry never re-sends to someone already reached.
    """
    from apps.core.tasks import send_email_task

    try:
        send_email_task.delay(subject, message, recipient)
        return True
    except Exception as exc:
        logger.error("Could not queue email to %s: %s", recipient, exc)
        return False


def _get_from_email() -> str:
    return getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        "WellTrip Thailand <welltripth@welltripthailand.com>",
    )


# ---------------------------------------------------------------------------
# 1. Email OTP Verification
# ---------------------------------------------------------------------------
def request_email_otp(email: str, purpose: str = "MERCHANT_REGISTER") -> tuple[bool, str]:
    """
    Generate and dispatch a 6-digit cryptographic OTP.
    Enforces a strict 60-second cooldown rate limit.
    """
    clean_email = email.strip().lower()
    now = timezone.now()

    # Rate limiting: Check if an OTP was sent within the past 60 seconds
    recent_otp = (
        EmailVerificationOTP.objects.filter(email=clean_email, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if recent_otp and (now - recent_otp.created_at).total_seconds() < 60:
        remaining_sec = 60 - int((now - recent_otp.created_at).total_seconds())
        return False, f"กรุณารออีก {remaining_sec} วินาทีก่อนขอรหัส OTP ใหม่อีกครั้ง"

    # Invalidate prior unused OTPs for this email and purpose
    EmailVerificationOTP.objects.filter(
        email=clean_email, purpose=purpose, is_used=False
    ).update(is_used=True)

    # Generate 6-digit random code
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = now + timedelta(minutes=10)

    EmailVerificationOTP.objects.create(
        email=clean_email,
        otp_code=code,
        purpose=purpose,
        expires_at=expires_at,
    )

    subject = f"[WellTrip] รหัสยืนยันตัวตนของคุณคือ {code}"
    message = (
        f"เรียน ผู้ใช้งานแพลตฟอร์ม WellTrip Thailand,\n\n"
        f"รหัสยืนยันตัวตน (OTP) ของคุณคือ: {code}\n\n"
        f"รหัสนี้จะหมดอายุภายใน 10 นาที (เวลา {expires_at.strftime('%H:%M น.')})\n"
        f"หากคุณไม่ได้เป็นผู้ทำรายการ โปรดละเว้นอีเมลฉบับนี้\n\n"
        f"ขอแสดงความนับถือ,\n"
        f"ทีมงาน WellTrip Sisaket Smart Wellness Tourism"
    )

    if not _queue_mail(subject, message, clean_email):
        return False, "ไม่สามารถส่งอีเมลได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง"
    return True, "ส่งรหัส OTP ไปยังอีเมลของท่านเรียบร้อยแล้ว"


def verify_email_otp(email: str, code: str, purpose: str = "MERCHANT_REGISTER") -> tuple[bool, str]:
    """Verify submitted 6-digit OTP code against database."""
    clean_email = email.strip().lower()
    clean_code = code.strip()

    otp_record = (
        EmailVerificationOTP.objects.filter(
            email=clean_email,
            otp_code=clean_code,
            purpose=purpose,
            is_used=False,
        )
        .order_by("-created_at")
        .first()
    )

    if not otp_record:
        return False, "รหัส OTP ไม่ถูกต้องหรือถูกใช้งานไปแล้ว"

    if timezone.now() > otp_record.expires_at:
        return False, "รหัส OTP หมดอายุแล้ว กรุณาขอรหัสใหม่"

    otp_record.is_used = True
    otp_record.save(update_fields=["is_used"])
    return True, "ยืนยันรหัส OTP สำเร็จ"


# ---------------------------------------------------------------------------
# 2. Admin Alert on New Merchant Application
# ---------------------------------------------------------------------------
def send_admin_new_merchant_alert(merchant_user) -> bool:
    """Notify system administrators when a community partner submits registration."""
    admin_email = getattr(settings, "ADMIN_EMAIL", "promlikit@sskru.ac.th")

    subject = f"[WellTrip Admin Alert] มีผู้ประกอบการยื่นขอเปิดร้านใหม่: {merchant_user.full_name or merchant_user.email}"
    message = (
        f"เรียน ผู้ดูแลระบบ WellTrip,\n\n"
        f"มีผู้ประกอบการชุมชนลงทะเบียนขอเปิดร้านใหม่ในระบบ:\n"
        f"- ชื่อผู้ติดต่อ: {merchant_user.full_name}\n"
        f"- อีเมล: {merchant_user.email}\n"
        f"- เบอร์โทรศัพท์: {merchant_user.phone_number or 'ไม่ได้ระบุ'}\n"
        f"- หมวดหมู่ผู้ประกอบการ: {merchant_user.get_role_display()}\n"
        f"- วันเวลาที่สมัคร: {merchant_user.date_joined.strftime('%Y-%m-%d %H:%M น.')}\n\n"
        f"ท่านสามารถตรวจสอบเอกสารและพิจารณาอนุมัติ (KYC) ได้ที่ศูนย์ปฏิบัติการแอดมิน:\n"
        f"{_site_url()}/accounts/admin-center/?tab=approvals\n\n"
        f"ระบบแจ้งเตือนอัตโนมัติ WellTrip Sisaket"
    )

    return _queue_mail(subject, message, admin_email)


# ---------------------------------------------------------------------------
# 3. Merchant KYC Approval / Rejection Decision
# ---------------------------------------------------------------------------
def send_merchant_kyc_decision(merchant_user, is_approved: bool, reason: str = "") -> bool:
    """Notify merchant of their KYC verification decision."""
    recipient = merchant_user.email
    portal_url = f"{_site_url()}/accounts/login/"

    if is_approved:
        subject = "[WellTrip] ยินดีด้วย! ร้านค้าของคุณได้รับการอนุมัติเปิดให้บริการแล้ว"
        message = (
            f"เรียน คุณ {merchant_user.full_name or merchant_user.email},\n\n"
            f"ทีมงาน WellTrip Sisaket ได้ทำการตรวจสอบเอกสารและอนุมัติร้านค้าของคุณเรียบร้อยแล้ว\n"
            f"รายการที่พัก บริการ หรือสินค้า OTOP ของคุณจะเปิดแสดงสู่สาธารณะและพร้อมรับการจองทันที\n\n"
            f"ท่านสามารถเข้าสู่ระบบเพื่อจัดการห้องพัก เมนู และสต็อกสินค้าได้ที่:\n"
            f"{portal_url}\n\n"
            f"ขอขอบคุณที่ร่วมเป็นส่วนหนึ่งในการขับเคลื่อนการท่องเที่ยวเชิงสุขภาวะจังหวัดศรีสะเกษ\n"
            f"ทีมงาน WellTrip Thailand"
        )
    else:
        subject = "[WellTrip] ผลการพิจารณาการลงทะเบียนร้านค้าของคุณ"
        reason_text = f"\nสาเหตุ: {reason}\n" if reason else ""
        message = (
            f"เรียน คุณ {merchant_user.full_name or merchant_user.email},\n\n"
            f"ทีมงาน WellTrip Sisaket ได้ตรวจสอบข้อมูลการลงทะเบียนร้านค้าของคุณแล้ว "
            f"พบว่ายังไม่ผ่านเกณฑ์การพิจารณาในครั้งนี้\n"
            f"{reason_text}\n"
            f"ท่านสามารถแก้ไขเอกสารหรือสอบถามเพิ่มเติมได้ที่ welltripth@welltripthailand.com\n\n"
            f"ทีมงาน WellTrip Thailand"
        )

    return _queue_mail(subject, message, recipient)


# ---------------------------------------------------------------------------
# 4. Payment Verified & Booking Confirmed Notification (Voucher)
# ---------------------------------------------------------------------------
def send_booking_voucher_and_order_alert(payment) -> bool:
    """
    Send digital booking voucher to Tourist and order alert to involved Merchants.
    """
    booking = payment.booking
    if not booking:
        return False

    tourist = getattr(booking, "customer", None) or getattr(booking, "user", None)
    tourist_email = tourist.email if tourist else None

    # Collect items summary
    items_summary = []
    merchant_emails = set()

    for item in booking.items.select_related("vendor"):
        items_summary.append(
            f"- {item.item_title_snapshot} (จำนวน: {item.quantity}, ราคา: ฿{item.unit_price_snapshot:,.2f})"
        )
        if item.vendor and item.vendor.email:
            merchant_emails.add(item.vendor.email)

    items_text = "\n".join(items_summary) if items_summary else f"- รหัสการจอง: {booking.booking_code}"

    # 1. Email to Tourist
    if tourist_email:
        tourist_subject = f"[WellTrip] ยืนยันการชำระเงินและเวาเชอร์การจอง ({booking.booking_code})"
        tourist_message = (
            f"เรียน คุณ {tourist.full_name or 'นักท่องเที่ยว'},\n\n"
            f"การชำระเงินสำหรับการจองของคุณได้รับการยืนยันเรียบร้อยแล้ว (CONFIRMED)\n\n"
            f"รายละเอียดการจอง:\n"
            f"- รหัสการจอง: {booking.booking_code}\n"
            f"- วันที่ทำรายการ: {timezone.now().strftime('%d/%m/%Y %H:%M น.')}\n"
            f"- ยอดเงินที่ชำระ: ฿{payment.amount:,.2f}\n"
            f"- ช่องทาง: โอนเงินผ่านธนาคารกสิกรไทย\n\n"
            f"รายการที่จอง:\n"
            f"{items_text}\n\n"
            f"ท่านสามารถแสดงหลักฐานหรือเปิดดูรายละเอียดการจองได้ที่:\n"
            f"{_site_url()}/bookings/detail/{booking.id}/\n\n"
            f"ขอให้ท่านมีความสุขกับการท่องเที่ยวเชิงสุขภาวะในจังหวัดศรีสะเกษ\n"
            f"ทีมงาน WellTrip Thailand"
        )
        _queue_mail(tourist_subject, tourist_message, tourist_email)

    # 2. Email to Merchants
    for m_email in merchant_emails:
        m_subject = f"[WellTrip] มีคำสั่งซื้อใหม่และได้รับการชำระเงินแล้ว ({booking.booking_code})"
        m_message = (
            f"เรียน ผู้ประกอบการ WellTrip,\n\n"
            f"มีนักท่องเที่ยวทำการจองและชำระเงินเรียบร้อยแล้ว:\n\n"
            f"- รหัสการจอง: {booking.booking_code}\n"
            f"- ยอดชำระ: ฿{payment.amount:,.2f}\n"
            f"- ผู้จอง: {tourist.full_name or tourist.email if tourist else 'นักท่องเที่ยว'}\n"
            f"- รายการที่จอง:\n{items_text}\n\n"
            f"ท่านสามารถตรวจสอบคิวงานและเตรียมการให้บริการได้ใน Partner Studio\n\n"
            f"ทีมงาน WellTrip Thailand"
        )
        _queue_mail(m_subject, m_message, m_email)

    return True


# ---------------------------------------------------------------------------
# 5. Payment Slip Rejected Alert
# ---------------------------------------------------------------------------
def send_slip_rejected_alert(payment, rejection_reason: str) -> bool:
    """Notify tourist when their uploaded slip failed verification."""
    booking = payment.booking
    if not booking:
        return False

    tourist = getattr(booking, "customer", None) or getattr(booking, "user", None)
    if not tourist or not tourist.email:
        return False

    tourist_email = tourist.email
    subject = f"[WellTrip] สลิปการชำระเงินไม่ผ่านการตรวจสอบ (รหัสการจอง: {booking.booking_code})"
    message = (
        f"เรียน คุณ {tourist.full_name or 'นักท่องเที่ยว'},\n\n"
        f"ระบบได้ทำการตรวจสอบสลิปการโอนเงินสำหรับการจองรหัส {booking.booking_code} แล้วพบว่า:\n\n"
        f"สาเหตุ: {rejection_reason}\n\n"
        f"การจองของท่านยังคงอยู่ในสถานะรอชำระเงิน โปรดแนบหลักฐานการโอนเงินที่ถูกต้องใหม่อีกครั้งได้ที่:\n"
        f"{_site_url()}/payments/instruction/{booking.id}/\n\n"
        f"หากท่านโอนเงินถูกต้องแล้วและมีข้อสงสัย โปรดติดต่อ welltripth@welltripthailand.com\n\n"
        f"ทีมงาน WellTrip Thailand"
    )

    return _queue_mail(subject, message, tourist_email)
