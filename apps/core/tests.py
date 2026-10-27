from django.test import TestCase, Client
from django.conf import settings
from django.contrib.auth.hashers import get_hasher


class SecuritySettingsTestCase(TestCase):
    """
    Automated Security Tests verifying non-negotiable security requirements.
    """

    def setUp(self):
        self.client = Client()

    def test_argon2_is_primary_password_hasher(self):
        """
        WHY: Argon2 is memory-hard and GPU-resistant.
        Verifies Argon2 is the first hasher in PASSWORD_HASHERS.
        """
        hasher = get_hasher('default')
        self.assertEqual(hasher.algorithm, 'argon2')

    def test_session_cookie_security_flags(self):
        """
        WHY: Prevents session theft via XSS (HttpOnly) and CSRF (SameSite=Lax).
        """
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        # Absolute session limit must not exceed 12 hours (43200s)
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 43200)

    def test_csrf_cookie_security_flags(self):
        """
        WHY: Prevents CSRF token extraction via client scripts.
        """
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')

    def test_browser_hardening_headers(self):
        """
        WHY: Prevents Clickjacking (X-Frame-Options: DENY) and MIME sniffing.
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_content_security_policy_present(self):
        """
        WHY: Restricts execution of unauthorized third-party scripts.
        """
        response = self.client.get('/')
        self.assertIn('Content-Security-Policy', response.headers)
        csp = response.headers.get('Content-Security-Policy')
        self.assertIn("default-src 'self'", csp)

    def test_home_page_injects_htmx_csrf(self):
        """
        WHY: Guarantees every AJAX/HTMX request passes Django's CSRF guard.
        """
        response = self.client.get('/')
        self.assertContains(response, 'hx-headers')
        self.assertContains(response, 'X-CSRFToken')


class NotificationServiceTestCase(TestCase):
    """
    Unit & Integration Tests for Hostinger Centralized SMTP Suite & Brand Assets.
    """

    def setUp(self):
        from django.core import mail
        mail.outbox = []
        from apps.accounts.models import User, UserRoles
        self.merchant = User.objects.create_user(
            email="merchant.test@welltrip.com",
            password="testPassword12345",
            first_name="สมศรี",
            last_name="ศรีสะเกษ",
            role=UserRoles.HOMESTAY_OWNER,
        )

    def test_request_email_otp_dispatches_mail_and_enforces_rate_limit(self):
        from django.core import mail
        from apps.core.services.notifications import request_email_otp, verify_email_otp
        from apps.accounts.models import EmailVerificationOTP

        # 1. First OTP request
        success, msg = request_email_otp("test@welltrip.com")
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[WellTrip] รหัสยืนยันตัวตนของคุณคือ", mail.outbox[0].subject)

        otp_obj = EmailVerificationOTP.objects.filter(email="test@welltrip.com").first()
        self.assertIsNotNone(otp_obj)
        self.assertEqual(len(otp_obj.otp_code), 6)

        # 2. Immediate second request must be blocked by 60s cooldown
        success2, msg2 = request_email_otp("test@welltrip.com")
        self.assertFalse(success2)
        self.assertIn("กรุณารออีก", msg2)

        # 3. Verification with wrong code
        ok, verify_msg = verify_email_otp("test@welltrip.com", "999999")
        self.assertFalse(ok)

        # 4. Verification with correct code
        ok, verify_msg = verify_email_otp("test@welltrip.com", otp_obj.otp_code)
        self.assertTrue(ok)
        otp_obj.refresh_from_db()
        self.assertTrue(otp_obj.is_used)

    def test_admin_new_merchant_alert(self):
        from django.core import mail
        from apps.core.services.notifications import send_admin_new_merchant_alert

        result = send_admin_new_merchant_alert(self.merchant)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("มีผู้ประกอบการยื่นขอเปิดร้านใหม่", mail.outbox[0].subject)
        self.assertIn(self.merchant.email, mail.outbox[0].body)

    def test_merchant_kyc_decision_notification(self):
        from django.core import mail
        from apps.core.services.notifications import send_merchant_kyc_decision

        # Test Approval
        result = send_merchant_kyc_decision(self.merchant, is_approved=True)
        self.assertTrue(result)
        self.assertIn("ยินดีด้วย! ร้านค้าของคุณได้รับการอนุมัติ", mail.outbox[0].subject)

        # Test Rejection
        mail.outbox = []
        result_reject = send_merchant_kyc_decision(self.merchant, is_approved=False, reason="เอกสารไม่ครบถ้วน")
        self.assertTrue(result_reject)
        self.assertIn("ผลการพิจารณาการลงทะเบียนร้านค้า", mail.outbox[0].subject)
        self.assertIn("เอกสารไม่ครบถ้วน", mail.outbox[0].body)

    def test_manifest_and_brand_assets_load(self):
        response = self.client.get('/manifest.json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "WellTrip - Smart Wellness Tourism")
        self.assertTrue(any("192" in icon["sizes"] for icon in data["icons"]))

