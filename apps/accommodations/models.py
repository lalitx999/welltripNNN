import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify
from apps.core.services.media import secure_upload_path


def accommodation_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="accommodations")


class AccommodationStatus(models.TextChoices):
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "รอการตรวจสอบ (Pending)"
    ACTIVE = "ACTIVE", "เปิดให้บริการ (Active)"
    SUSPENDED = "SUSPENDED", "ระงับชั่วคราว (Suspended)"


class Accommodation(models.Model):
    """
    Homestay domain model owned by a HOMESTAY_OWNER.
    Uses UUID primary key and RESTRICT on owner FK to protect order history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="accommodations",
    )
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    subdistrict = models.CharField(max_length=100, blank=True, default="")
    district = models.CharField(max_length=100, blank=True, default="")
    province = models.CharField(max_length=100, db_index=True, default="ศรีสะเกษ")
    postal_code = models.CharField(max_length=10, blank=True, default="")
    
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    status = models.CharField(
        max_length=30,
        choices=AccommodationStatus.choices,
        default=AccommodationStatus.PENDING_VERIFICATION,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accommodations"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} ({self.province})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.name, allow_unicode=True)}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)


class Room(models.Model):
    """A room type within an Accommodation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    accommodation = models.ForeignKey(
        Accommodation, on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=200)
    room_type = models.CharField(max_length=100, default="Standard")
    capacity_people = models.PositiveIntegerField(default=2)
    base_price_per_night = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    total_rooms_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "accommodation_rooms"
        ordering = ("base_price_per_night",)

    def __str__(self):
        return f"{self.name} - {self.accommodation.name}"


class RoomImage(models.Model):
    """Room gallery images, validated and stripped of EXIF data."""
    id = models.BigAutoField(primary_key=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=accommodation_image_path)
    is_cover = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "accommodation_room_images"
        ordering = ("order",)


class RoomPricingCalendar(models.Model):
    """
    Nightly availability and dynamic pricing record for a Room.
    This row is what checkout locks with select_for_update() to prevent race conditions.
    """
    id = models.BigAutoField(primary_key=True)
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="pricing_calendars"
    )
    date = models.DateField(db_index=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    available_count = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "accommodation_room_pricing"
        unique_together = ("room", "date")
        indexes = [
            models.Index(fields=["room", "date"]),
        ]

    def __str__(self):
        return f"{self.room.name} ({self.date}): ฿{self.price} ({self.available_count} left)"
