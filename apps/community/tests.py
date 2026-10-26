from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, UserRoles, AuditLog
from apps.community.models import MapLocation, PassportStamp, MapLocationCategory


class CommunityMapAndPassportSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 7:
    Verifies Digital Passport QR check-ins, Anti-duplicate stamping, and API responses.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.tourist = User.objects.create_user(
            email="tourist@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )

        self.location = MapLocation.objects.create(
            title="วัดป่ามหาเจดีย์แก้ว (วัดล้านขวด)",
            category=MapLocationCategory.PHOTO_SPOT,
            latitude=Decimal("14.6194000"),
            longitude=Decimal("104.4261000"),
            address="อ.ขุนหาญ จ.ศรีสะเกษ",
            qr_secret="TEST-SECRET-KHUNHAN-999",
            is_active=True,
        )

    def test_claim_stamp_awards_digital_stamp_and_logs_audit(self):
        """Tourist claiming valid QR secret receives a PassportStamp and creates AuditLog."""
        self.client.force_login(self.tourist)
        url = reverse('community:claim_stamp', kwargs={'qr_secret': self.location.qr_secret})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('community:passport'), response.url)

        stamp = PassportStamp.objects.filter(user=self.tourist, location=self.location).first()
        self.assertIsNotNone(stamp)

        # Verify AuditLog logged the stamp acquisition
        log = AuditLog.objects.filter(action="CREATE", model_name="PassportStamp", user=self.tourist).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['location_title'], self.location.title)

    def test_claim_stamp_anti_duplicate_check(self):
        """Scanning the same QR code multiple times does NOT create duplicate stamps."""
        self.client.force_login(self.tourist)
        url = reverse('community:claim_stamp', kwargs={'qr_secret': self.location.qr_secret})

        # Claim 1st time
        self.client.get(url)
        self.assertEqual(PassportStamp.objects.filter(user=self.tourist, location=self.location).count(), 1)

        # Claim 2nd time
        self.client.get(url)
        self.assertEqual(PassportStamp.objects.filter(user=self.tourist, location=self.location).count(), 1)

    def test_claim_stamp_invalid_secret_returns_404(self):
        """Invalid or non-existent QR secret must return HTTP 404."""
        self.client.force_login(self.tourist)
        url = reverse('community:claim_stamp', kwargs={'qr_secret': "INVALID-SECRET-CODE-XYZ"})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_locations_api_json_structure(self):
        """API returns correctly formatted coordinates for map markers."""
        url = reverse('community:locations_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('locations', data)
        self.assertEqual(len(data['locations']), 1)
        self.assertEqual(data['locations'][0]['title'], self.location.title)
        self.assertAlmostEqual(data['locations'][0]['lat'], 14.6194, places=3)
