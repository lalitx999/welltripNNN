import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.bookings.models import BookingStatus
from apps.bookings.services.checkout import process_checkout
from apps.core.geo import parse_coordinates
from apps.otop.models import OTOPProduct
from apps.payments.models import Payment, PaymentSlip, SlipVerificationStatus

MEDIA = tempfile.mkdtemp()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ShipmentEmailTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(email="seller@example.com", password="x", role=UserRoles.OTOP_OWNER)
        MerchantProfile.objects.create(user=self.seller, business_name="ร้านผ้าไหม", status=MerchantApprovalStatus.APPROVED)
        self.buyer = User.objects.create_user(email="buyer@example.com", password="x", role=UserRoles.TOURIST, first_name="สมหญิง")
        product = OTOPProduct.objects.create(owner=self.seller, name="ผ้าไหมลายลูกแก้ว", price=Decimal("500"), stock_quantity=5)
        self.booking = process_checkout(
            self.buyer, [{"item_type": "OTOP", "entity_id": str(product.id), "quantity": 1}],
            shipping_address={"recipient_name": "สมหญิง ใจดี", "phone_number": "0812345678", "address_line": "12 ม.3",
                              "district": "เมือง", "province": "ศรีสะเกษ", "postal_code": "33000"},
        )
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        self.item = self.booking.items.get()

    def test_orders_page_has_the_confirmation_modal(self):
        self.client.force_login(self.seller)
        page = self.client.get(reverse("accounts:portal_orders"))
        self.assertContains(page, 'id="ship-confirm"')
        self.assertContains(page, 'data-recipient="สมหญิง ใจดี (0812345678)"')
        self.assertContains(page, 'name="carrier"')

    def test_marking_shipped_emails_the_buyer_with_tracking(self):
        self.client.force_login(self.seller)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:portal_fulfillment", args=[self.item.id]), {
                "status": "SHIPPED", "tracking_number": "EF123456789TH", "carrier": "THAILAND_POST",
            })
        self.item.refresh_from_db()
        self.assertEqual(self.item.carrier, "THAILAND_POST")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["buyer@example.com"])
        self.assertIn(self.booking.booking_code, message.subject)
        self.assertIn("EF123456789TH", message.body)
        self.assertIn("https://track.thailandpost.co.th/?trackNumber=EF123456789TH", message.body)
        self.assertIn("สมหญิง ใจดี", message.body)

    def test_no_email_without_a_tracking_number(self):
        self.client.force_login(self.seller)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:portal_fulfillment", args=[self.item.id]), {"status": "SHIPPED", "tracking_number": " "})
        self.assertEqual(len(mail.outbox), 0)


@override_settings(MEDIA_ROOT=MEDIA)
class SlipReviewImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_review_page_shows_a_slip_that_was_already_checked(self):
        admin = User.objects.create_user(email="slip_admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        buyer = User.objects.create_user(email="slip_buyer@example.com", password="x")
        owner = User.objects.create_user(email="slip_owner@example.com", password="x", role=UserRoles.OTOP_OWNER)
        product = OTOPProduct.objects.create(owner=owner, name="กาแฟ", price=Decimal("100"), stock_quantity=3)
        booking = process_checkout(buyer, [{"item_type": "OTOP", "entity_id": str(product.id), "quantity": 1}])
        payment = Payment.objects.create(booking=booking, amount=booking.total_amount, status="FAILED")
        slip = PaymentSlip.objects.create(
            payment=payment, image=SimpleUploadedFile("s.jpg", b"x", content_type="image/jpeg"),
            verification_status=SlipVerificationStatus.REJECTED, verification_notes="ยอดเงินไม่ตรง",
        )
        self.client.force_login(admin)
        page = self.client.get(reverse("payments:admin_review", args=[payment.id]))
        self.assertContains(page, slip.image.url)
        self.assertContains(page, "ยอดเงินไม่ตรง")
        self.assertContains(page, "ไม่มีสลิปที่รอตรวจ")


class GoogleMapsLinkTests(TestCase):
    def test_place_pin_wins_over_the_map_centre(self):
        url = ("https://www.google.com/maps/place/Wat+Lan+Khuat/@14.6201,104.4150,17z/data=!3m1!4b1!4m6!3m5"
               "!1s0x311a!8m2!3d14.618459!4d104.4193077!16s")
        self.assertEqual(parse_coordinates(url), (Decimal("14.6184590"), Decimal("104.4193077")))

    def test_other_formats(self):
        self.assertEqual(parse_coordinates("15.1186, 104.3225"), (Decimal("15.1186000"), Decimal("104.3225000")))
        self.assertEqual(parse_coordinates("https://maps.google.com/?q=15.1,104.3")[0], Decimal("15.1000000"))
        self.assertEqual(parse_coordinates("https://www.google.com/maps/@15.2,104.4,16z")[1], Decimal("104.4000000"))
        self.assertEqual(parse_coordinates("ไม่มีพิกัด"), (None, None))

    def test_short_links_are_expanded_only_for_google_hosts(self):
        from apps.core.geo import coordinates_from_maps_input
        expanded = mock.Mock(url="https://www.google.com/maps/place/X/@1,1,1z/data=!3d15.11!4d104.32")
        with mock.patch("requests.get", return_value=expanded) as get:
            self.assertEqual(coordinates_from_maps_input("https://maps.app.goo.gl/abc")[0], Decimal("15.1100000"))
            coordinates_from_maps_input("https://evil.example.com/abc")
        self.assertEqual(get.call_count, 1)


class DeepSeekSettingsTests(TestCase):
    @override_settings(DEEPSEEK_API_KEY="k", DEEPSEEK_MODEL="deepseek-test-model", DEEPSEEK_BASE_URL="https://api.example.test")
    def test_configured_model_and_endpoint_are_used(self):
        from apps.ai_recommendations.services import analyze_health_deepseek
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch("apps.ai_recommendations.services.requests.post", return_value=reply) as post:
            analyze_health_deepseek({"bmi": 22, "bmr": 1400, "age": 30})
        self.assertEqual(post.call_args.args[0], "https://api.example.test/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-test-model")
