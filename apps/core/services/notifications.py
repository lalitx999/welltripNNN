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
from django.core.mail import send_mail
from django.utils import timezone
from apps.accounts.models import EmailVerificationOTP

logger = logging.getLogger(__name__)


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

    try:
        send_mail(subject, message, _get_from_email(), [clean_email], fail_silently=False)
        logger.info("Dispatched OTP %s to email %s", code, clean_email)
        return True, "ส่งรหัส OTP ไปยังอีเมลของท่านเรียบร้อยแล้ว"
    except Exception as exc:
        logger.error("Failed to send OTP email to %s: %s", clean_email, exc)
        return False, f"ไม่สามารถส่งอีเมลได้ในขณะนี้: {str(exc)}"


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
    from_email = _get_from_email()

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
        f"{getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')}/admin/\n\n"
        f"ระบบแจ้งเตือนอัตโนมัติ WellTrip Sisaket"
    )

    try:
        send_mail(subject, message, from_email, [admin_email], fail_silently=False)
        logger.info("Dispatched new merchant alert for %s to admin %s", merchant_user.email, admin_email)
        return True
    except Exception as exc:
        logger.error("Failed to send admin merchant alert: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 3. Merchant KYC Approval / Rejection Decision
# ---------------------------------------------------------------------------
def send_merchant_kyc_decision(merchant_user, is_approved: bool, reason: str = "") -> bool:
    """Notify merchant of their KYC verification decision."""
    from_email = _get_from_email()
    recipient = merchant_user.email
    portal_url = f"{getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')}/accounts/login/"

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

    try:
        send_mail(subject, message, from_email, [recipient], fail_silently=False)
        logger.info("Dispatched decision email to merchant %s (approved=%s)", recipient, is_approved)
        return True
    except Exception as exc:
        logger.error("Failed to send merchant decision email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 4. Payment Verified & Booking Confirmed Notification (Voucher)
# ---------------------------------------------------------------------------
def send_booking_voucher_and_order_alert(payment) -> bool:
    """
    Send digital booking voucher to Tourist and order alert to involved Merchants.
    """
    from_email = _get_from_email()
    booking = payment.booking
    if not booking:
        return False

    tourist = booking.user
    tourist_email = tourist.email if tourist else None

    # Collect items summary
    items_summary = []
    merchant_emails = set()

    for item in booking.items.all():
        name = getattr(item, "item_name", "รายการบริการ/ห้องพัก")
        qty = getattr(item, "quantity", 1)
        price = getattr(item, "unit_price", 0)
        items_summary.append(f"- {name} (จำนวน: {qty}, ราคา: ฿{price:,.2f})")

        # Collect vendor emails if linked
        room = getattr(item, "room", None)
        if room and room.accommodation and room.accommodation.owner:
            merchant_emails.add(room.accommodation.owner.email)
        service = getattr(item, "service", None)
        if service and service.owner:
            merchant_emails.add(service.owner.email)
        otop = getattr(item, "otop_product", None)
        if otop and otop.owner:
            merchant_emails.add(otop.owner.email)

    items_text = "\n".join(items_summary) if items_summary else f"- รหัสการจอง: #{str(booking.id)[:8].upper()}"

    # 1. Email to Tourist
    if tourist_email:
        tourist_subject = f"[WellTrip] ยืนยันการชำระเงินและเวาเชอร์การจอง (#{str(booking.id)[:8].upper()})"
        tourist_message = (
            f"เรียน คุณ {tourist.full_name or 'นักท่องเที่ยว'},\n\n"
            f"การชำระเงินสำหรับการจองของคุณได้รับการยืนยันเรียบร้อยแล้ว (CONFIRMED)\n\n"
            f"รายละเอียดการจอง:\n"
            f"- รหัสการจอง: #{str(booking.id)[:8].upper()}\n"
            f"- วันที่ทำรายการ: {timezone.now().strftime('%d/%m/%Y %H:%M น.')}\n"
            f"- ยอดเงินที่ชำระ: ฿{payment.amount:,.2f}\n"
            f"- ช่องทาง: โอนเงินผ่านธนาคารกสิกรไทย\n\n"
            f"รายการที่จอง:\n"
            f"{items_text}\n\n"
            f"ท่านสามารถแสดงหลักฐานหรือเปิดดูรายละเอียดการจองได้ที่:\n"
            f"{getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')}/bookings/{booking.id}/\n\n"
            f"ขอให้ท่านมีความสุขกับการท่องเที่ยวเชิงสุขภาวะในจังหวัดศรีสะเกษ\n"
            f"ทีมงาน WellTrip Thailand"
        )
        try:
            send_mail(tourist_subject, tourist_message, from_email, [tourist_email], fail_silently=False)
            logger.info("Dispatched payment confirmation voucher to %s", tourist_email)
        except Exception as exc:
            logger.error("Failed to send tourist voucher email: %s", exc)

    # 2. Email to Merchants
    for m_email in merchant_emails:
        m_subject = f"[WellTrip] มีคำสั่งซื้อใหม่และได้รับการชำระเงินแล้ว (#{str(booking.id)[:8].upper()})"
        m_message = (
            f"เรียน ผู้ประกอบการ WellTrip,\n\n"
            f"มีนักท่องเที่ยวทำการจองและชำระเงินเรียบร้อยแล้ว:\n\n"
            f"- รหัสการจอง: #{str(booking.id)[:8].upper()}\n"
            f"- ยอดชำระ: ฿{payment.amount:,.2f}\n"
            f"- ผู้จอง: {tourist.full_name or tourist.email if tourist else 'นักท่องเที่ยว'}\n"
            f"- รายการที่จอง:\n{items_text}\n\n"
            f"ท่านสามารถตรวจสอบคิวงานและเตรียมการให้บริการได้ใน Merchant Studio\n\n"
            f"ทีมงาน WellTrip Thailand"
        )
        try:
            send_mail(m_subject, m_message, from_email, [m_email], fail_silently=True)
            logger.info("Dispatched new order alert to merchant %s", m_email)
        except Exception as exc:
            logger.warning("Failed to send merchant order alert to %s: %s", m_email, exc)

    return True


# ---------------------------------------------------------------------------
# 5. Payment Slip Rejected Alert
# ---------------------------------------------------------------------------
def send_slip_rejected_alert(payment, rejection_reason: str) -> bool:
    """Notify tourist when their uploaded slip failed verification."""
    from_email = _get_from_email()
    booking = payment.booking
    if not booking or not booking.user or not booking.user.email:
        return False

    tourist_email = booking.user.email
    subject = f"[WellTrip] สลิปการชำระเงินไม่ผ่านการตรวจสอบ (รหัสการจอง: #{str(booking.id)[:8].upper()})"
    message = (
        f"เรียน คุณ {booking.user.full_name or 'นักท่องเที่ยว'},\n\n"
        f"ระบบได้ทำการตรวจสอบสลิปการโอนเงินสำหรับการจองรหัส #{str(booking.id)[:8].upper()} แล้วพบว่า:\n\n"
        f"สาเหตุ: {rejection_reason}\n\n"
        f"การจองของท่านยังคงอยู่ในสถานะรอชำระเงิน โปรดแนบหลักฐานการโอนเงินที่ถูกต้องใหม่อีกครั้งได้ที่:\n"
        f"{getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')}/payments/{payment.id}/\n\n"
        f"หากท่านโอนเงินถูกต้องแล้วและมีข้อสงสัย โปรดติดต่อ welltripth@welltripthailand.com\n\n"
        f"ทีมงาน WellTrip Thailand"
    )

    try:
        send_mail(subject, message, from_email, [tourist_email], fail_silently=False)
        logger.info("Dispatched slip rejection email to %s", tourist_email)
        return True
    except Exception as exc:
        logger.error("Failed to send slip rejection email: %s", exc)
        return False
