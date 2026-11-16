import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify
from apps.core.services.media import secure_upload_path
from django.utils.translation import gettext_lazy


def accommodation_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="accommodations")


class AccommodationStatus(models.TextChoices):
    PENDING_VERIFICATION = "PENDING_VERIFICATION", gettext_lazy("รอการตรวจสอบ (Pending)")
    ACTIVE = "ACTIVE", gettext_lazy("เปิดให้บริการ (Active)")
    SUSPENDED = "SUSPENDED", gettext_lazy("ระงับชั่วคราว (Suspended)")


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
    google_maps_url = models.URLField(max_length=500, blank=True, default="")

    # One photo for listings and the top of the detail page (a house's own photos stay on the house)
    profile_image = models.ImageField(upload_to=accommodation_image_path, null=True, blank=True)
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

    @property
    def min_price_per_night(self):
        first_room = self.rooms.filter(is_active=True).order_by('base_price_per_night').first()
        return first_room.base_price_per_night if first_room else None

    @property
    def min_customer_price(self):
        """Lowest nightly price a customer pays here (fee included), for listings."""
        from apps.core.pricing import customer_price
        return customer_price(self.min_price_per_night)

    @property
    def hero_image(self):
        if self.profile_image:
            return self.profile_image
        first_room = self.rooms.filter(is_active=True).first()
        if first_room:
            img = first_room.images.filter(is_cover=True).first() or first_room.images.first()
            if img and img.image:
                return img.image
        return None

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.name, allow_unicode=True)}-{uuid.uuid4().hex[:6]}"
        if self.google_maps_url:
            from apps.core.geo import coordinates_from_maps_input, parse_coordinates
            lat, lng = parse_coordinates(self.google_maps_url)
            if lat is None and self.latitude is None:
                # Short share link without numbers: expand it once, while we have no position yet
                lat, lng = coordinates_from_maps_input(self.google_maps_url)
            if lat is not None:
                self.latitude, self.longitude = lat, lng
        super().save(*args, **kwargs)


class RoomCooling(models.TextChoices):
    FAN = "FAN", gettext_lazy("ห้องพัดลม")
    AIR = "AIR", gettext_lazy("ห้องแอร์")
    BOTH = "BOTH", gettext_lazy("มีทั้งพัดลมและแอร์")


class RoomPricingMode(models.TextChoices):
    PER_HOUSE = "PER_HOUSE", gettext_lazy("เหมาจ่ายต่อห้อง/หลัง")
    PER_PERSON = "PER_PERSON", gettext_lazy("คิดต่อคน")


class Room(models.Model):
    """
    A house (or room type) inside an Accommodation. A community enterprise lists
    each member's house here under one account.

    Prices are what the owner receives per night: per house, or per guest when
    pricing_mode is PER_PERSON. base_price_per_night is the fan price (or the
    only price); a BOTH house also has air_price_per_night. Customers pay these
    plus the platform fee (apps.core.pricing).
    """
    MAX_IMAGES = 3
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
    cooling = models.CharField(max_length=8, choices=RoomCooling.choices, default=RoomCooling.FAN)
    air_price_per_night = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    pricing_mode = models.CharField(max_length=12, choices=RoomPricingMode.choices, default=RoomPricingMode.PER_HOUSE)
    total_rooms_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    @property
    def price_per_night(self):
        return self.base_price_per_night

    @property
    def is_per_person(self):
        return self.pricing_mode == RoomPricingMode.PER_PERSON

    def cooling_options(self):
        """The choices a guest picks from when booking: FAN, AIR or both."""
        if self.cooling == RoomCooling.BOTH:
            return [RoomCooling.FAN, RoomCooling.AIR]
        return [self.cooling]

    def owner_nightly_price(self, option, calendar_price=None):
        """
        Owner price for one night (per house or per guest) for the chosen cooling.
        A special calendar price replaces the base price; the air option keeps its
        surcharge over the fan price on top of it.
        """
        nightly = calendar_price if calendar_price is not None else self.base_price_per_night
        if option == RoomCooling.AIR and self.cooling == RoomCooling.BOTH and self.air_price_per_night:
            nightly = nightly + (self.air_price_per_night - self.base_price_per_night)
        return max(nightly, Decimal("0.01"))

    @property
    def customer_price(self):
        """Customer price of the first option (fan, or the only one)."""
        from apps.core.pricing import customer_price
        return customer_price(self.base_price_per_night)

    @property
    def customer_air_price(self):
        from apps.core.pricing import customer_price
        if self.cooling == RoomCooling.BOTH and self.air_price_per_night:
            return customer_price(self.air_price_per_night)
        return None

    @property
    def cover_image(self):
        images = list(self.images.all())
        return next((i for i in images if i.is_cover), images[0] if images else None)

    @property
    def capacity(self):
        return self.capacity_people

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
