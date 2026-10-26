from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRoles, AuditLog
from apps.accommodations.models import Accommodation, AccommodationStatus


class AdminOperationsSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 8:
    Verifies One-Time Merchant KYC Approval, Admin authorization,
    PWA Service Worker security boundaries, and custom error handling.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.admin = User.objects.create_user(
            email="admin_ops@example.com",
            password=self.password,
            role=UserRoles.COMMUNITY_ADMIN,
        )
        self.tourist = User.objects.create_user(
            email="tourist_regular@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )
        self.unapproved_merchant = User.objects.create_user(
            email="new_vendor@example.com",
            password=self.password,
            role=UserRoles.HOMESTAY_OWNER,
            email_verified=False,
            is_active=False,
        )
        self.pending_homestay = Accommodation.objects.create(
            owner=self.unapproved_merchant,
            name="บ้านสวนขุนหาญ",
            status=AccommodationStatus.PENDING_VERIFICATION,
        )

    def test_one_time_kyc_approval_activates_merchant_and_accommodations(self):
        """
        WHY: One-Time KYC eliminates ongoing admin bottlenecks by automatically
        activating both the vendor account and all their accommodations at once.
        """
        self.client.force_login(self.admin)
        url = reverse('accounts:admin_approve_merchant', kwargs={'user_id': self.unapproved_merchant.id})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        self.unapproved_merchant.refresh_from_db()
        self.assertTrue(self.unapproved_merchant.email_verified)
        self.assertTrue(self.unapproved_merchant.is_active)

        self.pending_homestay.refresh_from_db()
        self.assertEqual(self.pending_homestay.status, AccommodationStatus.ACTIVE)

        # Verify AuditLog logged ONE_TIME_KYC_APPROVED
        log = AuditLog.objects.filter(action="UPDATE", model_name="User", user=self.admin).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['action'], "ONE_TIME_KYC_APPROVED")

    def test_non_admin_cannot_approve_merchants(self):
        """Tourist is strictly blocked with HTTP 403 when attempting KYC approval."""
        self.client.force_login(self.tourist)
        url = reverse('accounts:admin_approve_merchant', kwargs={'user_id': self.unapproved_merchant.id})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

        self.unapproved_merchant.refresh_from_db()
        self.assertFalse(self.unapproved_merchant.email_verified)

    def test_service_worker_security_headers_and_cache_exclusion(self):
        """
        WHY: PWA Service Worker must NEVER cache /admin, /accounts, or /payments (Security #10).
        """
        url = reverse('core:service_worker')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Service-Worker-Allowed'), '/')
        sw_code = response.content.decode('utf-8')

        # Must explicitly forbid sensitive paths
        self.assertIn("url.pathname.startsWith('/admin')", sw_code)
        self.assertIn("url.pathname.startsWith('/accounts')", sw_code)
        self.assertIn("url.pathname.startsWith('/payments')", sw_code)
        self.assertIn("url.pathname.startsWith('/bookings')", sw_code)
