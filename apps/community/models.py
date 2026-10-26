import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models


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
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
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
