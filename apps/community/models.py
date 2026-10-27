import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.core.services.media import secure_upload_path


def story_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="stories")


class MapLocationCategory(models.TextChoices):
    HOMESTAY = "HOMESTAY", "โฮมสเตย์ / ที่พักชุมชน"
    FOOD = "FOOD", "ร้านอาหารสุขภาพ"
    WELLNESS = "WELLNESS", "ศูนย์นวดแผนไทยและสปา"
    OTOP = "OTOP", "ศูนย์จำหน่ายสินค้า OTOP"
    PHOTO_SPOT = "PHOTO_SPOT", "จุดถ่ายรูป / จุดเช็คอินธรรมชาติ"


class MapLocation(models.Model):
    """
    Physical coordinates and metadata for cultural/community sites in Sisaket.
    Carries a unique qr_secret used for Digital Passport check-ins.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150, db_index=True)
    category = models.CharField(
        max_length=50,
        choices=MapLocationCategory.choices,
        default=MapLocationCategory.PHOTO_SPOT,
        db_index=True,
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7, default=Decimal("15.1186000"))
    longitude = models.DecimalField(max_digits=10, decimal_places=7, default=Decimal("104.3225000"))
    google_maps_url = models.URLField(max_length=500, blank=True, default="")
    address = models.TextField(blank=True, default="")
    related_entity_id = models.CharField(max_length=36, blank=True, null=True)
    qr_secret = models.CharField(
        max_length=100,
        unique=True,
        default=uuid.uuid4,
        db_index=True,
        help_text="รหัสความลับเฉพาะสำหรับพิมพ์ลงบนป้าย QR ณ สถานที่จริง",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "map_locations"
        ordering = ("title",)

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class PassportStamp(models.Model):
    """
    Digital Passport Stamp collected by a tourist at a physical community venue.
    Enforces a unique constraint to prevent duplicate stamping of the same venue.
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="passport_stamps",
    )
    location = models.ForeignKey(
        MapLocation,
        on_delete=models.CASCADE,
        related_name="stamps",
    )
    stamped_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "passport_stamps"
        ordering = ("-stamped_at",)
        unique_together = ("user", "location")

    def __str__(self):
        return f"Stamp for {self.user.email} at {self.location.title}"


class UserPoints(models.Model):
    """
    Loyalty points balance earned from booking and passport stamp check-ins.
    Redeemable for discount vouchers in checkout.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="loyalty_points",
    )
    total_earned = models.IntegerField(default=0)
    current_balance = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_points"

    def __str__(self):
        return f"Points ({self.user.email}): {self.current_balance} pts"


class Coupon(models.Model):
    """
    Discount promotional vouchers with validity and minimum order thresholds.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    expires_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coupons"
        ordering = ("-created_at",)

    def is_valid_for(self, order_amount: Decimal) -> tuple[bool, str]:
        from django.utils import timezone
        if not self.is_active:
            return False, "คูปองนี้ถูกระงับการใช้งานแล้ว"
        if timezone.now() > self.expires_at:
            return False, "คูปองนี้หมดอายุการใช้งานแล้ว"
        if order_amount < self.min_purchase:
            return False, f"ยอดสั่งซื้อขั้นต่ำสำหรับคูปองนี้คือ ฿{self.min_purchase:,.2f}"
        return True, "ใช้คูปองส่วนลดสำเร็จ"

    def __str__(self):
        return f"Coupon {self.code} (-฿{self.discount_amount})"


class EditorialEntry(models.Model):
    """
    Cultural stories, community wisdom, festivals, and travel articles (Bilingual TH/EN).
    """
    class Kind(models.TextChoices):
        STORY = "STORY", "เรื่องเล่าชุมชน (Story)"
        COMMUNITY = "COMMUNITY", "วิสาหกิจชุมชน (Community)"
        ATTRACTION = "ATTRACTION", "แหล่งท่องเที่ยว (Attraction)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.STORY, db_index=True)
    title = models.CharField(max_length=200, db_index=True)
    title_en = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    summary_en = models.TextField(blank=True)
    body = models.TextField(blank=True)
    body_en = models.TextField(blank=True)
    image = models.ImageField(upload_to=story_image_path, null=True, blank=True)
    image_url = models.TextField(blank=True, default="")
    image_alt = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    google_maps_url = models.URLField(max_length=500, blank=True, default="")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "community_editorial_entries"
        ordering = ("-updated_at",)

    def __str__(self):
        return f"[{self.kind}] {self.title}"

    @property
    def content(self):
        """Backward-compatible alias for body."""
        return self.body

    @property
    def excerpt(self):
        """Backward-compatible alias for summary."""
        return self.summary or (self.body[:200] if self.body else "")

    @property
    def slug(self):
        """Backward-compatible alias returning str(self.id)."""
        return str(self.id)

    @property
    def display_image_url(self):
        if self.image:
            return self.image.url
        if self.image_url:
            return self.image_url
        return "/static/images/hero-default.jpg"


class LocationEvent(models.Model):
    """
    Consent-based, coarse GPS location log (rounded to 2 decimal places ~1.1km).
    Strictly complies with PDPA data minimization guidelines.
    """
    class Outcome(models.TextChoices):
        GRANTED = "granted", "ยินยอมระบุตำแหน่ง (Granted)"
        DENIED = "denied", "ปฏิเสธ (Denied)"
        UNAVAILABLE = "unavailable", "ไม่สามารถระบุได้ (Unavailable)"
        TIMEOUT = "timeout", "หมดเวลาเชื่อมต่อ (Timeout)"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_events",
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    latitude = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    longitude = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    consent_version = models.CharField(max_length=40, default="2026-10-coarse-v1")
    purpose = models.CharField(max_length=40, default="community_travel_experience")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "community_location_events"
        ordering = ("-created_at",)

    def __str__(self):
        return f"LocationEvent ({self.user.email}) - {self.outcome} at {self.created_at:%Y-%m-%d %H:%M}"

