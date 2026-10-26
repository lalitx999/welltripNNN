import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

BOOKING_TTL_MINUTES = 15


def generate_booking_code():
    """Generates WT-YYYYMMDD-XXXXXX format per spec."""
    date_part = timezone.now().strftime('%Y%m%d')
    random_part = secrets.token_hex(3).upper()
    return f"WT-{date_part}-{random_part}"


def default_expires_at():
    """15-minute payment countdown TTL."""
    return timezone.now() + timedelta(minutes=BOOKING_TTL_MINUTES)


class BookingStatus(models.TextChoices):
    AWAITING_PAYMENT = "AWAITING_PAYMENT", "รอชำระเงิน (Awaiting Payment)"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED", "หมดเวลาชำระเงิน (Expired)"
    CONFIRMED = "CONFIRMED", "ยืนยันแล้ว (Confirmed)"
    CANCELLED = "CANCELLED", "ยกเลิก (Cancelled)"
    COMPLETED = "COMPLETED", "เสร็จสิ้น (Completed)"


class BookingItemType(models.TextChoices):
    ROOM = "ROOM", "ที่พัก / โฮมสเตย์"
    FOOD = "FOOD", "อาหารสุขภาพ"
    WELLNESS = "WELLNESS", "นวดแผนไทย / สปา"
    OTOP = "OTOP", "สินค้าชุมชน OTOP"


class Booking(models.Model):
    """
    Main order entity. Holds multiple items across community vendors.
    Protected by strict 15-minute expiration countdown.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_code = models.CharField(
        max_length=30, unique=True, default=generate_booking_code, db_index=True
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="bookings",
    )
    status = models.CharField(
        max_length=30,
        choices=BookingStatus.choices,
        default=BookingStatus.AWAITING_PAYMENT,
        db_index=True,
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=Decimal("0.00"),
    )
    customer_notes = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(default=default_expires_at, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.booking_code} - {self.customer.email} (฿{self.total_amount})"

    @property
    def is_expired(self):
        return self.status == BookingStatus.AWAITING_PAYMENT and timezone.now() > self.expires_at

    @property
    def remaining_seconds(self):
        if self.status != BookingStatus.AWAITING_PAYMENT:
            return 0
        diff = (self.expires_at - timezone.now()).total_seconds()
        return max(0, int(diff))


class BookingItem(models.Model):
    """
    Polymorphic order item belonging to a specific community vendor.
    Prices are frozen in snapshot columns so later vendor price edits never rewrite history.
    """
    id = models.BigAutoField(primary_key=True)
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="items"
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="vendor_booking_items",
    )
    item_type = models.CharField(max_length=20, choices=BookingItemType.choices)
    entity_id = models.CharField(max_length=50)  # UUID or integer slot id
    item_title_snapshot = models.CharField(max_length=255)
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    booking_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "booking_items"
        indexes = [
            models.Index(fields=["vendor", "item_type"]),
        ]

    def __str__(self):
        return f"[{self.item_type}] {self.item_title_snapshot} x {self.quantity} (฿{self.subtotal})"
