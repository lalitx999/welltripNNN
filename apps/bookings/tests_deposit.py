import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accommodations.models import Accommodation, AccommodationStatus, Room, RoomPricingCalendar
from apps.accounts.models import AuditLog, MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.bookings.models import Booking, BookingStatus, PaymentPlan
from apps.bookings.services.checkout import StockUnavailableError, cancel_and_restore_expired_bookings, process_checkout
from apps.bookings.services.deposit import split_deposit
from apps.otop.models import OTOPProduct
from apps.payments.models import Payment, PaymentSlip, PaymentStatus, SlipVerificationStatus


def approved(email, role):
    user = User.objects.create_user(email=email, password="x", role=role)
    MerchantProfile.objects.create(user=user, business_name=email, status=MerchantApprovalStatus.APPROVED)
    return user


MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class DepositTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.owner = approved("dep_owner@example.com", UserRoles.HOMESTAY_OWNER)
        self.other_owner = approved("dep_other@example.com", UserRoles.HOMESTAY_OWNER)
        self.admin = User.objects.create_user(email="dep_admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.guest = User.objects.create_user(email="dep_guest@example.com", password="x", role=UserRoles.TOURIST)
        acc = Accommodation.objects.create(owner=self.owner, name="บ้านโนน", status=AccommodationStatus.ACTIVE)
        self.room = Room.objects.create(accommodation=acc, name="บ้านแม่บุญมา", base_price_per_night=Decimal("1000"), total_rooms_count=1)
        self.night = timezone.localdate() + timedelta(days=7)

    def line(self, room=None):
        return {"item_type": "ROOM", "entity_id": str((room or self.room).id), "quantity": 1, "date": self.night.isoformat(), "nights": 1}

    def book_deposit(self):
        return process_checkout(self.guest, [self.line()], payment_plan="DEPOSIT")

    def pay_slip(self, booking):
        payment = Payment.objects.create(booking=booking, amount=booking.amount_due_online)
        PaymentSlip.objects.create(
            payment=payment, image=SimpleUploadedFile("s.jpg", b"x", content_type="image/jpeg"),
            amount_seen=payment.amount, verification_status=SlipVerificationStatus.PENDING_CHECK,
        )
        payment.status = PaymentStatus.PENDING
        payment.save()
        return payment

    def available(self):
        return RoomPricingCalendar.objects.get(room=self.room, date=self.night).available_count

    def test_split_is_thirty_percent_in_whole_baht(self):
        self.assertEqual(split_deposit(Decimal("1050")), (Decimal("315"), Decimal("735")))
        self.assertEqual(split_deposit(Decimal("1001")), (Decimal("300"), Decimal("701")))  # 300.3 -> 300

    def test_deposit_booking_records_deposit_and_balance_and_holds_the_room(self):
        booking = self.book_deposit()
        self.assertEqual(booking.payment_plan, PaymentPlan.DEPOSIT)
        self.assertEqual(booking.total_amount, Decimal("1050.00"))
        self.assertEqual(booking.deposit_amount, Decimal("315"))
        self.assertEqual(booking.balance_due, Decimal("735"))
        self.assertEqual(booking.amount_due_online, Decimal("315"))
        self.assertEqual(self.available(), 0)

    def test_full_payment_still_takes_the_whole_amount(self):
        booking = process_checkout(self.guest, [self.line()])
        self.assertEqual(booking.amount_due_online, booking.total_amount)

    def test_deposit_only_for_houses_of_one_homestay(self):
        product = OTOPProduct.objects.create(owner=self.owner, name="ผ้า", price=Decimal("100"), stock_quantity=3)
        with self.assertRaises(StockUnavailableError):
            process_checkout(self.guest, [self.line(), {"item_type": "OTOP", "entity_id": str(product.id), "quantity": 1}], payment_plan="DEPOSIT")
        other = Accommodation.objects.create(owner=self.other_owner, name="บ้านอื่น", status=AccommodationStatus.ACTIVE)
        other_room = Room.objects.create(accommodation=other, name="อีกหลัง", base_price_per_night=Decimal("500"))
        with self.assertRaises(StockUnavailableError):
            process_checkout(self.guest, [self.line(), self.line(other_room)], payment_plan="DEPOSIT")

    def test_payment_page_asks_for_the_deposit_only(self):
        booking = self.book_deposit()
        self.client.force_login(self.guest)
        page = self.client.get(reverse("payments:payment_instruction", args=[booking.id]))
        self.assertEqual(Payment.objects.get(booking=booking).amount, Decimal("315.00"))
        self.assertContains(page, "735")

    def test_owner_confirms_deposit_then_records_balance_paid(self):
        booking = self.book_deposit()
        self.pay_slip(booking)
        self.client.force_login(self.owner)
        listing = self.client.get(reverse("bookings:stay_bookings"))
        self.assertContains(listing, booking.booking_code)
        self.client.post(reverse("bookings:stay_slip_review", args=[booking.id]), {"action": "APPROVE"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertTrue(booking.awaiting_balance)
        self.assertIn("ค้างชำระ", booking.status_label)
        self.assertEqual(self.available(), 0)  # locked to this guest

        self.client.post(reverse("bookings:stay_balance_paid", args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)
        self.assertEqual(booking.balance_received_by, self.owner)
        self.assertTrue(AuditLog.objects.filter(object_id=str(booking.id), changes__action="BALANCE_PAID").exists())

    def test_cancel_returns_the_room_and_needs_a_reason(self):
        booking = self.book_deposit()
        self.client.force_login(self.owner)
        self.client.post(reverse("bookings:stay_cancel", args=[booking.id]), {"reason": ""})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.AWAITING_PAYMENT)
        self.client.post(reverse("bookings:stay_cancel", args=[booking.id]), {"reason": "ลูกค้าแจ้งยกเลิก"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancel_reason, "ลูกค้าแจ้งยกเลิก")
        self.assertEqual(self.available(), 1)

    def test_admin_can_cancel_a_confirmed_deposit_booking(self):
        booking = self.book_deposit()
        booking.status = BookingStatus.CONFIRMED
        booking.save()
        self.client.force_login(self.admin)
        self.client.post(reverse("bookings:stay_cancel", args=[booking.id]), {"reason": "ที่พักปิดปรับปรุง"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(self.available(), 1)

    def test_unpaid_deposit_expires_and_frees_the_room(self):
        booking = self.book_deposit()
        Booking.objects.filter(id=booking.id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_and_restore_expired_bookings()
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PAYMENT_EXPIRED)
        self.assertEqual(self.available(), 1)

    def test_other_owners_cannot_touch_the_booking(self):
        booking = self.book_deposit()
        self.pay_slip(booking)
        self.client.force_login(self.other_owner)
        self.assertNotContains(self.client.get(reverse("bookings:stay_bookings") + "?tab=all"), booking.booking_code)
        self.client.post(reverse("bookings:stay_slip_review", args=[booking.id]), {"action": "APPROVE"})
        self.client.post(reverse("bookings:stay_cancel", args=[booking.id]), {"reason": "x"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.AWAITING_PAYMENT)

    def test_owner_cannot_approve_full_payment_slips(self):
        booking = process_checkout(self.guest, [self.line()])
        self.pay_slip(booking)
        self.client.force_login(self.owner)
        self.client.post(reverse("bookings:stay_slip_review", args=[booking.id]), {"action": "APPROVE"})
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.AWAITING_PAYMENT)

    def test_review_page_offers_the_deposit_for_houses_only(self):
        self.client.force_login(self.guest)
        session = self.client.session
        session["cart"] = [{
            "item_type": "ROOM", "entity_id": str(self.room.id), "title": "บ้าน", "price": "1050", "quantity": 1,
            "date": self.night.isoformat(), "nights": 1, "stay_total": "1050", "cooling": "FAN", "guests": 2,
        }]
        session.save()
        page = self.client.get(reverse("bookings:review"))
        self.assertContains(page, 'value="DEPOSIT"')
        self.assertContains(page, "฿315")
