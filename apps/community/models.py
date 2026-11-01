import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.core.services.media import secure_upload_path
from django.utils.translation import gettext as _, gettext_lazy


def story_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="stories")


class MapLocationCategory(models.TextChoices):
    HOMESTAY = "HOMESTAY", gettext_lazy("โฮมสเตย์ / ที่พักชุมชน")
    FOOD = "FOOD", gettext_lazy("ร้านอาหารสุขภาพ")
    WELLNESS = "WELLNESS", gettext_lazy("ศูนย์นวดแผนไทยและสปา")
    OTOP = "OTOP", gettext_lazy("ศูนย์จำหน่ายสินค้า OTOP")
    PHOTO_SPOT = "PHOTO_SPOT", gettext_lazy("จุดถ่ายรูป / จุดเช็คอินธรรมชาติ")


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
        help_text=gettext_lazy("รหัสความลับเฉพาะสำหรับพิมพ์ลงบนป้าย QR ณ สถานที่จริง"),
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
            return False, _("คูปองนี้ถูกระงับการใช้งานแล้ว")
        if timezone.now() > self.expires_at:
            return False, _("คูปองนี้หมดอายุการใช้งานแล้ว")
        if order_amount < self.min_purchase:
            return False, _("ยอดสั่งซื้อขั้นต่ำสำหรับคูปองนี้คือ ฿{min_purchase:,.2f}").format(min_purchase=self.min_purchase)
        return True, _("ใช้คูปองส่วนลดสำเร็จ")

    def __str__(self):
        return f"Coupon {self.code} (-฿{self.discount_amount})"


class EditorialEntry(models.Model):
    """
    Cultural stories, community wisdom, festivals, and travel articles (Bilingual TH/EN).
    """
    class Kind(models.TextChoices):
        STORY = "STORY", gettext_lazy("เรื่องเล่าชุมชน (Story)")
        COMMUNITY = "COMMUNITY", gettext_lazy("วิสาหกิจชุมชน (Community)")
        ATTRACTION = "ATTRACTION", gettext_lazy("แหล่งท่องเที่ยว (Attraction)")

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
        GRANTED = "granted", gettext_lazy("ยินยอมระบุตำแหน่ง (Granted)")
        DENIED = "denied", gettext_lazy("ปฏิเสธ (Denied)")
        UNAVAILABLE = "unavailable", gettext_lazy("ไม่สามารถระบุได้ (Unavailable)")
        TIMEOUT = "timeout", gettext_lazy("หมดเวลาเชื่อมต่อ (Timeout)")

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



def event_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="events")


class Event(models.Model):
    """
    A dated happening in Sisaket (festival, concert, contest, sports...).
    Shown on the events calendar and homepage until end_date passes.
    """

    class Category(models.TextChoices):
        FESTIVAL = "FESTIVAL", gettext_lazy("เทศกาลและงานประเพณี")
        MUSIC = "MUSIC", gettext_lazy("ดนตรีและคอนเสิร์ต")
        CONTEST = "CONTEST", gettext_lazy("การประกวด")
        SPORT = "SPORT", gettext_lazy("กีฬา")
        FOOD = "FOOD", gettext_lazy("อาหารและกาแฟ")
        OUTDOOR = "OUTDOOR", gettext_lazy("แคมป์และกิจกรรมกลางแจ้ง")
        OTHER = "OTHER", gettext_lazy("อื่นๆ")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.FESTIVAL)
    summary = models.TextField(blank=True)
    summary_en = models.TextField(blank=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    # Free-text override for split schedules, e.g. "12–13 และ 19–20 ธ.ค."
    date_note = models.CharField(max_length=120, blank=True)
    date_note_en = models.CharField(max_length=120, blank=True)
    venue = models.CharField(max_length=200, blank=True)
    venue_en = models.CharField(max_length=200, blank=True)
    google_maps_url = models.URLField(max_length=500, blank=True, default="")
    check_in_point = models.ForeignKey(
        MapLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    organizer = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True, default="")
    image = models.ImageField(upload_to=event_image_path, null=True, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "community_events"
        ordering = ("start_date", "title")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="event_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.start_date:%Y-%m-%d})"
