"""
Regression tests for the mock-data cleanup and security hardening pass:
real client IP behind nginx, open redirect, private payment slips,
no invented catalog figures, and the create_admin command.
"""
import io
import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings

from apps.accommodations.models import Accommodation, AccommodationStatus, Room
from apps.accounts.models import User, UserRoles
from apps.accounts.services.audit import get_client_ip
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.checkout import StockUnavailableError, process_checkout
from apps.payments.models import Payment, PaymentSlip, PaymentStatus

PASSWORD = "SecurePassword123!"


class ClientIpTestCase(TestCase):
    def test_prefers_nginx_real_ip_over_spoofable_forwarded_for(self):
        request = RequestFactory().get(
            "/", REMOTE_ADDR="172.18.0.5", HTTP_X_REAL_IP="203.0.113.7",
            HTTP_X_FORWARDED_FOR="6.6.6.6",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_falls_back_to_remote_addr_without_proxy(self):
        request = RequestFactory().get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6")
        self.assertEqual(get_client_ip(request), "127.0.0.1")


class LoginRedirectTestCase(TestCase):
    def setUp(self):
        User.objects.create_user(email="t@example.com", password=PASSWORD, role=UserRoles.TOURIST)

    def _login(self, next_url):
        return self.client.post(
            f"/accounts/login/?next={next_url}",
            {"email": "t@example.com", "password": PASSWORD, "username": "t@example.com"},
        )

    def test_rejects_protocol_relative_next(self):
        response = self._login("//evil.example.com/phish")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response.url)

    def test_allows_local_next(self):
        response = self._login("/bookings/my/")
        self.assertEqual(response.url, "/bookings/my/")


class DjangoAdminDisabledTestCase(TestCase):
    def test_builtin_admin_is_gone(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)


class PrivateSlipTestCase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD, role=UserRoles.TOURIST)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD, role=UserRoles.TOURIST)
        self.admin = User.objects.create_user(email="adm@example.com", password=PASSWORD, role=UserRoles.COMMUNITY_ADMIN)
        booking = Booking.objects.create(
            customer=self.owner, total_amount=Decimal("100.00"), status=BookingStatus.AWAITING_PAYMENT,
        )
        payment = Payment.objects.create(booking=booking, amount=booking.total_amount, status=PaymentStatus.PENDING)
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="JPEG")
        self.slip = PaymentSlip.objects.create(
            payment=payment, image=SimpleUploadedFile("s.jpg", buf.getvalue(), content_type="image/jpeg"),
        )
        self.url = "/media/" + self.slip.image.name

    def test_anonymous_cannot_fetch_slip(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_other_customer_cannot_fetch_slip(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_owner_and_admin_can_fetch_slip(self):
        for user in (self.owner, self.admin):
            self.client.force_login(user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")


class NoInventedDataTestCase(TestCase):
    def setUp(self):
        owner = User.objects.create_user(email="h@example.com", password=PASSWORD, role=UserRoles.HOMESTAY_OWNER)
        self.acc = Accommodation.objects.create(owner=owner, name="บ้านทดสอบ", status=AccommodationStatus.ACTIVE)

    def test_accommodation_without_rooms_has_no_price(self):
        self.assertIsNone(self.acc.min_price_per_night)

    def test_landing_shows_real_counts_only(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        values = [s["value"] for s in response.context["stats"]]
        self.assertEqual(values, [1, 0, 0])
        for item in response.context["featured_experiences"]:
            self.assertNotIn("rating", item)

    def test_price_filter_works(self):
        Room.objects.create(accommodation=self.acc, name="ห้อง A", base_price_per_night=Decimal("500"))
        response = self.client.get("/accommodations/?price=budget")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "บ้านทดสอบ")
        response = self.client.get("/accommodations/?price=luxury")
        self.assertNotContains(response, "บ้านทดสอบ")

    def test_checkout_never_invents_a_room(self):
        tourist = User.objects.create_user(email="c@example.com", password=PASSWORD, role=UserRoles.TOURIST)
        cart = [{"item_type": "ROOM", "entity_id": str(self.acc.id), "quantity": 1, "date": "2026-12-01"}]
        with self.assertRaises(StockUnavailableError):
            process_checkout(tourist, cart)
        self.assertFalse(Room.objects.exists())


class CreateAdminCommandTestCase(TestCase):
    def test_creates_super_admin_with_prompted_password(self):
        with mock.patch("getpass.getpass", side_effect=["Str0ng-Pass!word", "Str0ng-Pass!word"]):
            call_command("create_admin", "Boss@Example.com", stdout=io.StringIO())
        user = User.objects.get(email="boss@example.com")
        self.assertEqual(user.role, UserRoles.SUPER_ADMIN)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("Str0ng-Pass!word"))

    def test_rejects_mismatched_password(self):
        with mock.patch("getpass.getpass", side_effect=["Str0ng-Pass!word", "different"]):
            with self.assertRaises(CommandError):
                call_command("create_admin", "boss@example.com", stdout=io.StringIO())
        self.assertFalse(User.objects.exists())


class PassportSecretTestCase(TestCase):
    """The stamp QR secret proves an on-site visit, so public pages must not leak it."""

    def setUp(self):
        from apps.community.models import MapLocation
        self.loc = MapLocation.objects.create(
            title="ผามออีแดง", category=MapLocation._meta.get_field("category").choices[0][0],
            latitude=Decimal("14.4"), longitude=Decimal("104.7"), qr_secret="SECRET-ONSITE-123",
        )

    def test_map_page_and_api_do_not_expose_qr_secret(self):
        for url in ("/community/map/", "/community/api/locations/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, "SECRET-ONSITE-123")


class MerchantApprovalGateTestCase(TestCase):
    """Partner Studio is only usable after an admin approves the merchant's KYC."""

    def setUp(self):
        from apps.accounts.models import MerchantApprovalStatus, MerchantProfile
        self.merchant = User.objects.create_user(email="m@example.com", password=PASSWORD, role=UserRoles.OTOP_OWNER)
        self.profile = MerchantProfile.objects.create(
            user=self.merchant, business_name="ร้านทดสอบ", status=MerchantApprovalStatus.PENDING,
        )
        self.approved = MerchantApprovalStatus.APPROVED

    def test_pending_merchant_sees_waiting_page(self):
        self.client.force_login(self.merchant)
        response = self.client.get("/accounts/portal/")
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "accounts/merchant_pending.html")

    def test_approved_merchant_can_enter_portal(self):
        self.profile.status = self.approved
        self.profile.save()
        self.client.force_login(self.merchant)
        self.assertEqual(self.client.get("/accounts/portal/").status_code, 200)

    def test_tourist_signup_cannot_pick_a_merchant_role(self):
        self.client.post("/accounts/register/", {
            "first_name": "ก", "last_name": "ข", "email": "sneaky@example.com",
            "phone_number": "0812345678", "role": UserRoles.HOMESTAY_OWNER,
            "password": "Str0ng-Pass!word", "confirm_password": "Str0ng-Pass!word",
        })
        self.assertFalse(User.objects.filter(email="sneaky@example.com", role=UserRoles.HOMESTAY_OWNER).exists())


class ServerSidePricingTestCase(TestCase):
    """Cart prices come from the database, and multi-night stays book every night."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        owner = User.objects.create_user(email="o@example.com", password=PASSWORD, role=UserRoles.HOMESTAY_OWNER)
        acc = Accommodation.objects.create(owner=owner, name="บ้านริมทุ่ง", status=AccommodationStatus.ACTIVE)
        self.room = Room.objects.create(accommodation=acc, name="ห้องวิวนา", base_price_per_night=Decimal("800"))
        self.check_in = timezone.localdate() + timedelta(days=7)
        self.check_out = self.check_in + timedelta(days=3)
        self.tourist = User.objects.create_user(email="t2@example.com", password=PASSWORD, role=UserRoles.TOURIST)

    def _add_room(self, **extra):
        data = {
            "item_type": "ROOM", "entity_id": str(self.room.id), "quantity": 1,
            "check_in": self.check_in.isoformat(), "check_out": self.check_out.isoformat(),
            "price": "1", "title": "ห้องฟรี",
        }
        data.update(extra)
        return self.client.post("/bookings/cart/add/", data)

    def test_posted_price_and_title_are_ignored(self):
        self._add_room()
        item = self.client.session["cart"][0]
        self.assertEqual(Decimal(item["price"]), Decimal("800"))
        self.assertEqual(item["nights"], 3)
        self.assertIn("ห้องวิวนา", item["title"])

    def test_invalid_dates_are_rejected(self):
        self._add_room(check_out=self.check_in.isoformat())
        self.assertEqual(self.client.session.get("cart", []), [])

    def test_checkout_charges_and_reserves_every_night(self):
        from apps.accommodations.models import RoomPricingCalendar
        self._add_room()
        cart = self.client.session["cart"]
        booking = process_checkout(self.tourist, cart)
        self.assertEqual(booking.total_amount, Decimal("2400.00"))
        self.assertEqual(RoomPricingCalendar.objects.filter(room=self.room).count(), 3)

    def test_expiry_job_survives_service_only_wellness_items(self):
        from apps.bookings.models import BookingItem
        from apps.bookings.services.checkout import cancel_and_restore_expired_bookings
        from apps.services.models import WellnessService
        from django.utils import timezone
        spa = WellnessService.objects.create(owner=self.room.accommodation.owner, name="นวด", price=Decimal("300"))
        booking = Booking.objects.create(
            customer=self.tourist, total_amount=Decimal("300"), status=BookingStatus.AWAITING_PAYMENT,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        BookingItem.objects.create(
            booking=booking, vendor=spa.owner, item_type="WELLNESS", entity_id=str(spa.id),
            item_title_snapshot="นวด", unit_price_snapshot=spa.price, quantity=1, subtotal=spa.price,
            booking_metadata={"duration_minutes": 60},
        )
        self.assertEqual(cancel_and_restore_expired_bookings(), 1)


class PaymentInstructionTestCase(TestCase):
    def test_payment_page_uses_payee_from_settings(self):
        tourist = User.objects.create_user(email="pay@example.com", password=PASSWORD, role=UserRoles.TOURIST)
        booking = Booking.objects.create(customer=tourist, total_amount=Decimal("500"), status=BookingStatus.AWAITING_PAYMENT)
        self.client.force_login(tourist)
        with self.settings(PAYEE_ACCOUNT_NUMBER="999-9-99999-9"):
            response = self.client.get(f"/payments/instruction/{booking.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "999-9-99999-9")


class StudioFormsTestCase(TestCase):
    """The studio pages post the field names their forms expect."""

    def _merchant(self, role):
        from apps.accounts.models import MerchantApprovalStatus, MerchantProfile
        user = User.objects.create_user(email=f"{role.lower()}@example.com", password=PASSWORD, role=role)
        MerchantProfile.objects.create(user=user, business_name="ร้าน", status=MerchantApprovalStatus.APPROVED)
        self.client.force_login(user)
        return user

    def test_otop_studio_renders_stock_field(self):
        self._merchant(UserRoles.OTOP_OWNER)
        self.assertContains(self.client.get("/otop/studio/"), 'name="stock_quantity"')

    def test_wellness_slot_can_be_created(self):
        from apps.services.models import WellnessService, WellnessTimeSlot
        owner = self._merchant(UserRoles.WELLNESS_OWNER)
        spa = WellnessService.objects.create(owner=owner, name="นวด", price=Decimal("300"))
        self.client.post("/services/studio/wellness/slot/create/", {
            "service_id": str(spa.id), "date": "2026-12-01", "start_time": "09:00",
            "end_time": "10:00", "capacity_total": 3,
        })
        slot = WellnessTimeSlot.objects.get(service=spa)
        self.assertEqual((slot.capacity_total, slot.capacity_available), (3, 3))

    def test_new_homestay_is_hidden_until_published(self):
        self._merchant(UserRoles.HOMESTAY_OWNER)
        self.client.get("/accommodations/studio/")
        acc = Accommodation.objects.get()
        self.assertEqual(acc.status, AccommodationStatus.PENDING_VERIFICATION)
        self.client.post(f"/accommodations/studio/?acc_id={acc.id}", {"accommodation_id": acc.id, "status_action": "publish"})
        acc.refresh_from_db()
        self.assertEqual(acc.status, AccommodationStatus.PENDING_VERIFICATION)  # no rooms yet
        Room.objects.create(accommodation=acc, name="ห้อง", base_price_per_night=Decimal("500"))
        self.client.post(f"/accommodations/studio/?acc_id={acc.id}", {"accommodation_id": acc.id, "status_action": "publish"})
        acc.refresh_from_db()
        self.assertEqual(acc.status, AccommodationStatus.ACTIVE)


class AdminHierarchyTestCase(TestCase):
    """Community admins cannot escalate to, or take over, super admin accounts."""

    def setUp(self):
        self.super = User.objects.create_user(email="boss@example.com", password=PASSWORD, role=UserRoles.SUPER_ADMIN)
        self.community = User.objects.create_user(email="ca@example.com", password=PASSWORD, role=UserRoles.COMMUNITY_ADMIN)
        self.client.force_login(self.community)

    def test_cannot_promote_self_to_super_admin(self):
        self.client.post(f"/accounts/admin/users/{self.community.id}/edit/", {"role": UserRoles.SUPER_ADMIN})
        self.community.refresh_from_db()
        self.assertEqual(self.community.role, UserRoles.COMMUNITY_ADMIN)

    def test_cannot_create_super_admin(self):
        self.client.post("/accounts/admin/users/add/", {
            "email": "new@example.com", "role": UserRoles.SUPER_ADMIN, "password": "Str0ng-Pass!word",
        })
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_cannot_reset_or_suspend_super_admin(self):
        self.client.post(f"/accounts/admin/users/{self.super.id}/reset-password/", {"new_password": "Takeover-Pass!99"})
        self.client.post(f"/accounts/admin/users/{self.super.id}/toggle/")
        self.super.refresh_from_db()
        self.assertTrue(self.super.check_password(PASSWORD))
        self.assertTrue(self.super.is_active)

    def test_admin_created_accounts_need_a_strong_password(self):
        self.client.post("/accounts/admin/users/add/", {"email": "weak@example.com", "role": UserRoles.TOURIST, "password": ""})
        self.client.post("/accounts/admin/users/add/", {"email": "weak2@example.com", "role": UserRoles.TOURIST, "password": "123"})
        self.assertFalse(User.objects.filter(email__startswith="weak").exists())


class LogoutAndCspTestCase(TestCase):
    def test_logout_rejects_get(self):
        user = User.objects.create_user(email="lo@example.com", password=PASSWORD, role=UserRoles.TOURIST)
        self.client.force_login(user)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.client.post("/accounts/logout/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pages_load_no_third_party_scripts_or_styles(self):
        response = self.client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        for host in ("cdn.tailwindcss.com", "unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis.com"):
            self.assertNotIn(host, csp)
            self.assertNotContains(response, host)
