import io
from decimal import Decimal
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, UserRoles, AuditLog
from apps.bookings.models import Booking, BookingStatus
from apps.payments.models import Payment, PaymentSlip, PaymentStatus, SlipVerificationStatus


class PaymentSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 6:
    Verifies Anti-duplicate bank reference defense, IDOR protection,
    and administrative payment verification authorization.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.tourist1 = User.objects.create_user(
            email="tourist1@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )
        self.tourist2 = User.objects.create_user(
            email="tourist2@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password=self.password,
            role=UserRoles.COMMUNITY_ADMIN,
        )

        self.booking1 = Booking.objects.create(
            customer=self.tourist1,
            total_amount=Decimal("1200.00"),
            status=BookingStatus.AWAITING_PAYMENT,
        )
        self.payment1 = Payment.objects.create(
            booking=self.booking1,
            amount=self.booking1.total_amount,
            status=PaymentStatus.PENDING,
        )

    def _create_mock_image(self):
        img = Image.new("RGB", (80, 80), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile("slip.jpg", buf.read(), content_type="image/jpeg")

    def test_payment_instruction_idor_protection(self):
        """Tourist 2 cannot view or upload slip for Tourist 1's booking."""
        self.client.force_login(self.tourist2)
        url = reverse('payments:payment_instruction', kwargs={'booking_id': self.booking1.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('bookings:my_bookings'), response.url)

    def test_anti_duplicate_bank_reference_db_guard(self):
        """
        WHY: Stops replay attacks where an attacker submits the same bank receipt twice.
        The DB UniqueConstraint must reject identical references on verified slips.
        """
        image1 = self._create_mock_image()
        image2 = self._create_mock_image()

        # Slip 1 is verified
        slip1 = PaymentSlip.objects.create(
            payment=self.payment1,
            image=image1,
            provider_reference="KBANK-TXN-99999",
            verification_status=SlipVerificationStatus.VERIFIED,
        )

        booking2 = Booking.objects.create(
            customer=self.tourist2,
            total_amount=Decimal("500.00"),
            status=BookingStatus.AWAITING_PAYMENT,
        )
        payment2 = Payment.objects.create(
            booking=booking2,
            amount=booking2.total_amount,
            status=PaymentStatus.PENDING,
        )

        # Attempting to verify slip 2 with the identical reference must crash with IntegrityError
        with self.assertRaises(IntegrityError):
            PaymentSlip.objects.create(
                payment=payment2,
                image=image2,
                provider_reference="KBANK-TXN-99999",
                verification_status=SlipVerificationStatus.VERIFIED,
            )

    def test_admin_payment_approval_confirms_booking(self):
        """Admin approval verifies slip, marks payment success, and confirms booking."""
        slip = PaymentSlip.objects.create(
            payment=self.payment1,
            image=self._create_mock_image(),
            provider_reference="KBANK-12345",
            verification_status=SlipVerificationStatus.PENDING_CHECK,
        )

        self.client.force_login(self.admin)
        url = reverse('payments:admin_review', kwargs={'payment_id': self.payment1.id})

        response = self.client.post(url, {
            'action': 'APPROVE',
            'verification_notes': 'สลิปตรงยอดเงิน',
        })
        self.assertEqual(response.status_code, 302)

        self.payment1.refresh_from_db()
        self.assertEqual(self.payment1.status, PaymentStatus.SUCCESS)

        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.status, BookingStatus.CONFIRMED)

        slip.refresh_from_db()
        self.assertEqual(slip.verification_status, SlipVerificationStatus.VERIFIED)
        self.assertEqual(slip.verified_by, self.admin)

        # Verify AuditLog logged PAYMENT_APPROVED
        log = AuditLog.objects.filter(action="UPDATE", model_name="Payment", user=self.admin).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['action'], "PAYMENT_APPROVED")

    def test_non_admin_cannot_access_admin_payments(self):
        """Tourist is strictly blocked from the admin payment center with 403."""
        self.client.force_login(self.tourist1)
        url = reverse('payments:admin_list')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
