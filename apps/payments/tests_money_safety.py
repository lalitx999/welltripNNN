"""
Money-safety rules added after the Nov 2026 review:
receiver account check, booking-state checks, stock release, vendor access, coupon limits.
"""
import io
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import User, UserRoles
from apps.bookings.models import Booking, BookingItem, BookingStatus
from apps.bookings.services.checkout import cancel_and_restore_expired_bookings
from apps.community.models import Coupon
from apps.payments.models import Payment, PaymentSlip, PaymentStatus, SlipVerificationStatus
from apps.payments.services import account_matches_payee, review_slip, verify_slip_automatically

OUR_ACCOUNT = {"account": {"bank": {"type": "BANKAC", "account": "xxx-x-x0448-x"}}}
OTHER_ACCOUNT = {"account": {"bank": {"type": "BANKAC", "account": "xxx-x-x9999-x"}}}


def _image():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color="green").save(buf, format="JPEG")
    return SimpleUploadedFile("s.jpg", buf.getvalue(), content_type="image/jpeg")


def _provider(receiver, amount="1500.00", ref="REF-OK-1", duplicate=False):
    def provider(image):
        return {
            "amount": Decimal(amount),
            "trans_ref": ref,
            "trans_datetime": timezone.now(),
            "sender_name": "ลูกค้า",
            "receiver": receiver,
            "is_duplicate": duplicate,
        }
    return provider


class AccountMatchTestCase(TestCase):
    def test_masked_account_matches_only_our_digits(self):
        self.assertTrue(account_matches_payee("xxx-x-x0448-x", "001-1-50448-5"))
        self.assertFalse(account_matches_payee("xxx-x-x0449-x", "001-1-50448-5"))
        self.assertFalse(account_matches_payee("xxx-x-xxxxx-x", "001-1-50448-5"))  # nothing visible
        self.assertFalse(account_matches_payee("", "001-1-50448-5"))


class SlipSafetyTestCase(TestCase):
    def setUp(self):
        self.tourist = User.objects.create_user(email="t@example.com", password="x", role=UserRoles.TOURIST)
        self.admin = User.objects.create_user(email="a@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.booking = Booking.objects.create(
            customer=self.tourist, total_amount=Decimal("1500.00"), status=BookingStatus.AWAITING_PAYMENT
        )
        self.payment = Payment.objects.create(booking=self.booking, amount=Decimal("1500.00"))
        self.slip = PaymentSlip.objects.create(payment=self.payment, image=_image())

    def test_slip_paid_to_another_account_goes_to_admin(self):
        ok, slip, reason = verify_slip_automatically(self.slip.id, provider_func=_provider(OTHER_ACCOUNT))
        self.assertFalse(ok)
        self.assertEqual(slip.verification_status, SlipVerificationStatus.PENDING_CHECK)
        self.assertIn("บัญชีผู้รับ", slip.verification_notes)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.AWAITING_PAYMENT)

    def test_slip_paid_to_our_account_confirms(self):
        ok, slip, _ = verify_slip_automatically(self.slip.id, provider_func=_provider(OUR_ACCOUNT))
        self.assertTrue(ok)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    def test_promptpay_proxy_from_settings_counts_as_ours(self):
        proxy = {"account": {"proxy": {"type": "BILLERID", "account": "004999024969106"}}}
        with self.settings(PAYEE_PROXY_ACCOUNTS=["004999024969106"]):
            ok, _, _ = verify_slip_automatically(self.slip.id, provider_func=_provider(proxy))
        self.assertTrue(ok)

    def test_easyslip_duplicate_flag_goes_to_admin(self):
        ok, slip, _ = verify_slip_automatically(self.slip.id, provider_func=_provider(OUR_ACCOUNT, duplicate=True))
        self.assertFalse(ok)
        self.assertEqual(slip.verification_status, SlipVerificationStatus.PENDING_CHECK)

    def test_expired_booking_is_never_auto_confirmed(self):
        Booking.objects.filter(pk=self.booking.pk).update(status=BookingStatus.PAYMENT_EXPIRED)
        ok, slip, _ = verify_slip_automatically(self.slip.id, provider_func=_provider(OUR_ACCOUNT))
        self.assertFalse(ok)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PAYMENT_EXPIRED)

    def test_admin_cannot_approve_expired_booking(self):
        Booking.objects.filter(pk=self.booking.pk).update(status=BookingStatus.PAYMENT_EXPIRED)
        request = type("R", (), {"user": self.admin, "META": {}})()
        ok, message = review_slip(request, self.payment.id, "APPROVE")
        self.assertFalse(ok)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)

    def test_admin_approve_confirms_awaiting_booking(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payments:admin_review", args=[self.payment.id]), {"action": "APPROVE"})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    def test_upload_after_timer_ran_out_is_refused(self):
        Booking.objects.filter(pk=self.booking.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.tourist)
        self.client.post(reverse("payments:payment_instruction", args=[self.booking.id]), {"image": _image()})
        self.assertEqual(PaymentSlip.objects.filter(payment=self.payment).count(), 1)


class VendorPaymentAccessTestCase(TestCase):
    def test_vendor_in_booking_cannot_see_payment_or_slip(self):
        tourist = User.objects.create_user(email="c@example.com", password="x", role=UserRoles.TOURIST)
        vendor = User.objects.create_user(email="v@example.com", password="x", role=UserRoles.OTOP_OWNER)
        booking = Booking.objects.create(customer=tourist, total_amount=Decimal("100"), status=BookingStatus.AWAITING_PAYMENT)
        BookingItem.objects.create(
            booking=booking, vendor=vendor, item_type="OTOP", entity_id="1",
            item_title_snapshot="กาแฟ", unit_price_snapshot=Decimal("100"), subtotal=Decimal("100"),
        )
        payment = Payment.objects.create(booking=booking, amount=Decimal("100"))
        slip = PaymentSlip.objects.create(payment=payment, image=_image())

        self.client.force_login(vendor)
        page = self.client.get(reverse("payments:payment_instruction", args=[booking.id]))
        self.assertEqual(page.status_code, 302)
        self.assertEqual(self.client.get("/media/" + slip.image.name).status_code, 404)


class ExpiryJobTestCase(TestCase):
    def setUp(self):
        self.tourist = User.objects.create_user(email="e@example.com", password="x", role=UserRoles.TOURIST)

    def _expired_booking(self):
        return Booking.objects.create(
            customer=self.tourist, total_amount=Decimal("100"), status=BookingStatus.AWAITING_PAYMENT,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

    def test_unpaid_booking_expires(self):
        booking = self._expired_booking()
        self.assertEqual(cancel_and_restore_expired_bookings(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PAYMENT_EXPIRED)

    def test_booking_with_slip_waiting_for_review_is_kept(self):
        booking = self._expired_booking()
        payment = Payment.objects.create(booking=booking, amount=Decimal("100"))
        PaymentSlip.objects.create(payment=payment, image=_image())
        self.assertEqual(cancel_and_restore_expired_bookings(), 0)

    def test_beat_schedule_runs_the_job(self):
        from config.celery import app
        tasks = {entry["task"] for entry in app.conf.beat_schedule.values()}
        self.assertIn("apps.bookings.tasks.expire_unpaid_bookings_task", tasks)


class CouponLimitTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@example.com", password="x", role=UserRoles.TOURIST)
        self.coupon = Coupon.objects.create(
            code="WELCOME50", discount_amount=Decimal("50"), expires_at=timezone.now() + timedelta(days=5)
        )

    def _use(self, user, status=BookingStatus.CONFIRMED):
        Booking.objects.create(customer=user, total_amount=Decimal("100"), status=status, coupon_code="WELCOME50")

    def test_one_use_per_person_by_default(self):
        self.assertTrue(self.coupon.check_usage(self.user)[0])
        self._use(self.user)
        self.assertFalse(self.coupon.check_usage(self.user)[0])

    def test_expired_orders_give_the_use_back(self):
        self._use(self.user, status=BookingStatus.PAYMENT_EXPIRED)
        self.assertTrue(self.coupon.check_usage(self.user)[0])

    def test_total_limit(self):
        self.coupon.max_uses = 1
        self.coupon.per_user_limit = 0
        self.coupon.save()
        other = User.objects.create_user(email="o@example.com", password="x", role=UserRoles.TOURIST)
        self._use(other)
        self.assertFalse(self.coupon.check_usage(self.user)[0])
