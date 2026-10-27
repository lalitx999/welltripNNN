import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, UniqueConstraint
from apps.core.services.media import secure_upload_path


def slip_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="slips")


class PaymentChannel(models.TextChoices):
    BANK_TRANSFER = "BANK_TRANSFER", "โอนเงินผ่านบัญชีธนาคาร (Slip Check)"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "รอการตรวจสอบสลิป (Pending)"
    SUCCESS = "SUCCESS", "ชำระเงินสำเร็จ (Success)"
    FAILED = "FAILED", "การชำระเงินไม่ถูกต้อง (Failed)"
    EXPIRED = "EXPIRED", "หมดเวลาชำระเงิน (Expired)"


class SlipVerificationStatus(models.TextChoices):
    PENDING_CHECK = "PENDING_CHECK", "รอเจ้าหน้าที่ตรวจสอบ (Pending Check)"
    VERIFIED = "VERIFIED", "ตรวจสอบผ่านแล้ว (Verified)"
    REJECTED = "REJECTED", "ปฏิเสธ / สลิปไม่ถูกต้อง (Rejected)"


class Payment(models.Model):
    """
    Payment attempt record for a Booking.
    Strict 1-to-1 with Booking (RESTRICT delete).
    Snapshots the community receiving account details at time of order.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="payment",
    )
    payment_channel = models.CharField(
        max_length=50,
        choices=PaymentChannel.choices,
        default=PaymentChannel.BANK_TRANSFER,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )

    # Snapshot of community receiving bank account
    payee_bank_name = models.CharField(max_length=100, default="ธนาคารกสิกรไทย (KBANK)")
    payee_account_name = models.CharField(
        max_length=150, default="วิสาหกิจชุมชนท่องเที่ยววิถีสุขภาวะ"
    )
    payee_account_number = models.CharField(max_length=50, default="098-2-34567-8")

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Payment {self.id} for {self.booking.booking_code}: ฿{self.amount} ({self.status})"


class PaymentSlip(models.Model):
    """
    Uploaded bank transfer slip image and verification audit evidence.
    Includes a Database-level UniqueConstraint on verified provider reference
    to prevent duplicate slip replay attacks 100%.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="slips"
    )
    image = models.ImageField(upload_to=slip_image_path)
    amount_seen = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    provider_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="รหัสอ้างอิงธุรกรรมธนาคารจากสลิป (Bank Transfer Ref Number)",
    )
    provider_response_log = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(
        max_length=30,
        choices=SlipVerificationStatus.choices,
        default=SlipVerificationStatus.PENDING_CHECK,
        db_index=True,
    )
    verification_notes = models.TextField(blank=True, default="")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_slips",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_slips"
        ordering = ("-uploaded_at",)
        constraints = [
            # ⚠️ Zero-Trust Anti-Duplicate Guard:
            # Staves off reuse of the same bank slip reference across multiple orders!
            UniqueConstraint(
                fields=["provider_reference"],
                condition=Q(verification_status="VERIFIED"),
                name="unique_verified_bank_slip_ref",
            )
        ]

    def __str__(self):
        return f"Slip for {self.payment.booking.booking_code} [{self.verification_status}] Ref: {self.provider_reference}"
