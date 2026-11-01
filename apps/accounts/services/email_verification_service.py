"""
Email OTP verification for self-registered accounts.
A merchant reaches the admin KYC queue, and triggers the admin alert, only once verified.
"""
from apps.core.services import notifications

OTP_PURPOSE = "ACCOUNT_REGISTER"


def send_verification_code(user) -> tuple[bool, str]:
    return notifications.request_email_otp(user.email, purpose=OTP_PURPOSE)


def confirm_verification_code(user, code: str) -> tuple[bool, str]:
    """Check the code, mark the email verified and alert admins about new merchants."""
    verified, message = notifications.verify_email_otp(user.email, code, purpose=OTP_PURPOSE)
    if not verified:
        return False, message

    user.email_verified = True
    user.save(update_fields=["email_verified"])

    if user.is_merchant:
        notifications.send_admin_new_merchant_alert(user)
    return True, message
