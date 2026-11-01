import smtplib
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import EmailVerificationOTP, MerchantProfile, User, UserRoles
from apps.accounts.services import email_verification_service
from apps.core.services.notifications import (
    OTP_MAX_ATTEMPTS,
    OTP_MAX_PER_HOUR,
    request_email_otp,
    verify_email_otp,
)
from apps.core.tasks import send_otp_email_task

PASSWORD = "Str0ng-Pass!word"
PURPOSE = email_verification_service.OTP_PURPOSE


def latest_code(email):
    return EmailVerificationOTP.objects.filter(email=email).order_by("-created_at").first().otp_code


def wrong_code_for(email):
    return "111111" if latest_code(email) != "111111" else "222222"


def age_otps(email, **delta):
    """Move existing OTPs into the past so the send cooldown no longer applies."""
    EmailVerificationOTP.objects.filter(email=email).update(created_at=timezone.now() - timedelta(**delta))


@override_settings(ADMIN_EMAIL="admin@example.com")
class SignupVerificationFlowTestCase(TestCase):
    def register_tourist(self, email="new@example.com"):
        return self.client.post(reverse("accounts:register"), {
            "first_name": "ก", "last_name": "ข", "email": email, "phone_number": "0812345678",
            "role": UserRoles.TOURIST, "password": PASSWORD, "confirm_password": PASSWORD,
        })

    def register_merchant(self, email="shop@example.com"):
        return self.client.post(reverse("accounts:register_merchant"), {
            "business_category": "HOMESTAY", "first_name": "ก", "last_name": "ข",
            "phone_number": "0812345678", "email": email,
            "password": PASSWORD, "confirm_password": PASSWORD, "business_name": "บ้านสวน",
        })

    def test_signup_sends_code_without_logging_in(self):
        response = self.register_tourist()

        self.assertRedirects(response, reverse("accounts:verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertIn(latest_code("new@example.com"), mail.outbox[0].body)
        self.assertTrue(User.objects.get(email="new@example.com").needs_email_verification)

    def test_correct_code_verifies_and_logs_in(self):
        self.register_tourist()

        response = self.client.post(reverse("accounts:verify_email"), {"code": latest_code("new@example.com")})

        self.assertRedirects(response, reverse("core:home"))
        self.assertIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.get(email="new@example.com").email_verified)

    def test_wrong_code_stays_logged_out(self):
        self.register_tourist()

        response = self.client.post(reverse("accounts:verify_email"), {"code": wrong_code_for("new@example.com")})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.get(email="new@example.com").email_verified)

    def test_malformed_code_does_not_use_an_attempt(self):
        self.register_tourist()

        self.client.post(reverse("accounts:verify_email"), {"code": "12ab"})

        self.assertEqual(EmailVerificationOTP.objects.get(email="new@example.com").failed_attempts, 0)

    def test_unverified_login_goes_back_to_verification(self):
        self.register_tourist()
        self.client.session.flush()
        self.client.cookies.clear()

        response = self.client.post(reverse("accounts:login"), {"email": "new@example.com", "password": PASSWORD})

        self.assertRedirects(response, reverse("accounts:verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_login_with_wrong_password_reveals_nothing(self):
        self.register_tourist()
        self.client.session.flush()
        self.client.cookies.clear()

        response = self.client.post(reverse("accounts:login"), {"email": "new@example.com", "password": "wrong"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("pending_verification_user_id", self.client.session)

    def test_accounts_from_before_otp_still_log_in(self):
        User.objects.create_user(email="old@example.com", password=PASSWORD)

        response = self.client.post(reverse("accounts:login"), {"email": "old@example.com", "password": PASSWORD})

        self.assertRedirects(response, reverse("core:home"))
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(mail.outbox, [])

    def test_verify_page_needs_a_pending_signup(self):
        self.assertRedirects(self.client.get(reverse("accounts:verify_email")), reverse("accounts:login"))

    def test_resend_respects_cooldown_then_sends_new_code(self):
        self.register_tourist()

        self.client.post(reverse("accounts:resend_verification"))
        self.assertEqual(len(mail.outbox), 1)

        age_otps("new@example.com", minutes=2)
        old_code = latest_code("new@example.com")
        with mock.patch("apps.core.services.notifications.secrets.randbelow", return_value=(int(old_code) - 100000 + 1) % 900000):
            self.client.post(reverse("accounts:resend_verification"))
        self.assertEqual(len(mail.outbox), 2)

        response = self.client.post(reverse("accounts:verify_email"), {"code": old_code})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_merchant_reaches_admin_only_after_verifying(self):
        self.client.post(reverse("accounts:register_merchant"), {})  # invalid form sends nothing
        self.register_merchant()
        self.assertEqual([m.to[0] for m in mail.outbox], ["shop@example.com"])

        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD, role=UserRoles.SUPER_ADMIN)
        other_client = self.client_class()
        other_client.force_login(admin)
        page = other_client.get("/accounts/admin-center/?tab=approvals")
        self.assertNotContains(page, "shop@example.com")

        self.client.post(reverse("accounts:verify_email"), {"code": latest_code("shop@example.com")})

        self.assertEqual([m.to[0] for m in mail.outbox], ["shop@example.com", "admin@example.com"])
        self.assertTrue(MerchantProfile.objects.filter(user__email="shop@example.com").exists())
        page = other_client.get("/accounts/admin-center/?tab=approvals")
        self.assertContains(page, "shop@example.com")


class OtpServiceTestCase(TestCase):
    email = "otp@example.com"

    def test_wrong_guesses_burn_the_code(self):
        request_email_otp(self.email, purpose=PURPOSE)
        code = latest_code(self.email)
        wrong = wrong_code_for(self.email)

        for _ in range(OTP_MAX_ATTEMPTS):
            ok, _msg = verify_email_otp(self.email, wrong, purpose=PURPOSE)
            self.assertFalse(ok)

        ok, _msg = verify_email_otp(self.email, code, purpose=PURPOSE)
        self.assertFalse(ok)

    def test_code_expires(self):
        request_email_otp(self.email, purpose=PURPOSE)
        code = latest_code(self.email)
        EmailVerificationOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        ok, _msg = verify_email_otp(self.email, code, purpose=PURPOSE)

        self.assertFalse(ok)

    def test_code_works_only_once(self):
        request_email_otp(self.email, purpose=PURPOSE)
        code = latest_code(self.email)

        self.assertTrue(verify_email_otp(self.email, code, purpose=PURPOSE)[0])
        self.assertFalse(verify_email_otp(self.email, code, purpose=PURPOSE)[0])

    def test_hourly_cap(self):
        for _ in range(OTP_MAX_PER_HOUR):
            self.assertTrue(request_email_otp(self.email, purpose=PURPOSE)[0])
            age_otps(self.email, minutes=2)

        self.assertFalse(request_email_otp(self.email, purpose=PURPOSE)[0])

    def test_mail_shows_expiry_in_bangkok_time(self):
        request_email_otp(self.email, purpose=PURPOSE)
        otp = EmailVerificationOTP.objects.get(email=self.email)

        self.assertIn(timezone.localtime(otp.expires_at).strftime("%H:%M น."), mail.outbox[0].body)

    def test_failed_queue_does_not_start_cooldown(self):
        with mock.patch.object(send_otp_email_task, "apply_async", side_effect=ConnectionError("broker down")):
            self.assertFalse(request_email_otp(self.email, purpose=PURPOSE)[0])

        self.assertFalse(EmailVerificationOTP.objects.filter(email=self.email).exists())
        self.assertTrue(request_email_otp(self.email, purpose=PURPOSE)[0])

    def test_otp_mail_retries_stay_short(self):
        self.assertIn(smtplib.SMTPException, send_otp_email_task.autoretry_for)
        self.assertLessEqual(send_otp_email_task.max_retries, 3)
        self.assertLessEqual(send_otp_email_task.retry_backoff_max, 60)
