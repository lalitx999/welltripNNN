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

    def test_claim_stamp_awards_loyalty_points(self):
        """Claiming a stamp awards 50 points to tourist's UserPoints."""
        from apps.community.models import UserPoints
        self.client.force_login(self.tourist)
        url = reverse('community:claim_stamp', kwargs={'qr_secret': self.location.qr_secret})
        self.client.get(url)

        points = UserPoints.objects.filter(user=self.tourist).first()
        self.assertIsNotNone(points)
        self.assertEqual(points.current_balance, 50)

    def test_coupon_validation_and_threshold(self):
        """Verifies promo code minimum threshold validation."""
        from datetime import timedelta
        from django.utils import timezone
        from apps.community.models import Coupon

        coupon = Coupon.objects.create(
            code="SAVE100",
            discount_amount=Decimal("100.00"),
            min_purchase=Decimal("500.00"),
            expires_at=timezone.now() + timedelta(days=10),
            is_active=True,
        )

        # 1. Order below threshold (400 < 500)
        is_ok, msg = coupon.is_valid_for(Decimal("400.00"))
        self.assertFalse(is_ok)
        self.assertIn("ยอดสั่งซื้อขั้นต่ำ", msg)

        # 2. Order meeting threshold (600 >= 500)
        is_ok2, msg2 = coupon.is_valid_for(Decimal("600.00"))
        self.assertTrue(is_ok2)

        # 3. HTMX endpoint test
        url = reverse('community:validate_coupon')
        response = self.client.post(url, {"coupon_code": "SAVE100", "order_amount": "800.00"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "-฿100.00")
        self.assertContains(response, "฿700.00")

    def test_stories_list_and_detail_views(self):
        """Verifies editorial story directory and reader."""
        from apps.community.models import EditorialEntry
        story = EditorialEntry.objects.create(
            title="ตำนานผ้าไหมย้อมมะเกลือ",
            summary="ภูมิปัญญาการย้อมผ้าไหมธรรมชาติ",
            body="เนื้อหาบทความประวัติศาสตร์และวิธีการย้อม",
            is_published=True,
        )

        list_resp = self.client.get(reverse('community:stories_list'))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, story.title)

        detail_resp = self.client.get(reverse('community:story_detail', kwargs={'story_id': story.id}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, story.title)
        self.assertContains(detail_resp, story.summary)

    def test_location_events_purge_delete(self):
        """PDPA Compliance: User can delete their location logs via DELETE method."""
        from datetime import timedelta
        from django.utils import timezone
        from apps.community.models import LocationEvent

        LocationEvent.objects.create(
            user=self.tourist,
            outcome=LocationEvent.Outcome.GRANTED,
            latitude=Decimal("14.62"),
            longitude=Decimal("104.42"),
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertEqual(LocationEvent.objects.filter(user=self.tourist).count(), 1)

        self.client.force_login(self.tourist)
        url = reverse('community:my_location_events')
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], True)
        self.assertEqual(LocationEvent.objects.filter(user=self.tourist).count(), 0)



class EventCalendarTestCase(TestCase):
    """Events calendar: public listing hides past/draft events; only admins manage them."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.accounts.models import User, UserRoles
        from apps.community.models import Event

        today = timezone.localdate()
        self.upcoming = Event.objects.create(
            title="เทศกาลกาแฟ", title_en="Coffee Festival", start_date=today + timedelta(days=3),
            end_date=today + timedelta(days=5), is_published=True,
        )
        self.past = Event.objects.create(
            title="งานที่จบแล้ว", start_date=today - timedelta(days=10), end_date=today - timedelta(days=8), is_published=True,
        )
        self.draft = Event.objects.create(
            title="ฉบับร่าง", start_date=today + timedelta(days=1), end_date=today + timedelta(days=1),
        )
        self.admin = User.objects.create_user(email="ev-admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.tourist = User.objects.create_user(email="ev-t@example.com", password="x", role=UserRoles.TOURIST)

    def test_list_shows_only_published_upcoming(self):
        response = self.client.get("/community/events/")
        self.assertContains(response, "เทศกาลกาแฟ")
        self.assertNotContains(response, "งานที่จบแล้ว")
        self.assertNotContains(response, "ฉบับร่าง")
        self.assertEqual(self.client.get(f"/community/events/{self.draft.id}/").status_code, 404)

    def test_english_site_uses_english_fields(self):
        self.client.cookies["django_language"] = "en"
        response = self.client.get(f"/community/events/{self.upcoming.id}/")
        self.assertContains(response, "Coffee Festival")
        self.assertContains(response, "calendar.google.com")

    def test_only_admins_can_create_events(self):
        payload = {"title": "ลอยกระทง", "category": "FESTIVAL", "start_date": "2026-11-23", "end_date": "2026-11-24", "is_published": "on"}
        self.client.force_login(self.tourist)
        self.assertEqual(self.client.post("/accounts/admin/events/add/", payload).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post("/accounts/admin/events/add/", payload).status_code, 302)
        self.assertTrue(_event_exists("ลอยกระทง"))

    def test_end_before_start_is_rejected(self):
        self.client.force_login(self.admin)
        payload = {"title": "ผิดวัน", "category": "OTHER", "start_date": "2026-12-05", "end_date": "2026-12-01"}
        response = self.client.post("/accounts/admin/events/add/", payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(_event_exists("ผิดวัน"))


def _event_exists(title):
    from apps.community.models import Event
    return Event.objects.filter(title=title).exists()


class LanguageSwitchTestCase(TestCase):
    def test_switch_to_english_and_back(self):
        self.assertContains(self.client.get("/"), "หน้าหลัก")
        response = self.client.post("/i18n/setlang/", {"language": "en", "next": "/otop/"})
        self.assertRedirects(response, "/otop/", fetch_redirect_response=False)
        page = self.client.get("/")
        self.assertContains(page, 'lang="en"')
        self.assertContains(page, "Rest your mind in")
        self.client.post("/i18n/setlang/", {"language": "th", "next": "/"})
        self.assertContains(self.client.get("/"), "พักใจที่")

    def test_switch_ignores_offsite_next(self):
        response = self.client.post("/i18n/setlang/", {"language": "en", "next": "https://evil.example/"})
        self.assertEqual(response["Location"], "/")
