import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from apps.core.services.media import secure_upload_path


def service_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="services")


class FoodWellnessCategory(models.TextChoices):
    LOW_SUGAR = "LOW_SUGAR", "น้ำตาลน้อย (Low Sugar)"
    LOW_SODIUM = "LOW_SODIUM", "โซเดียมต่ำ (Low Sodium)"
    ORGANIC = "ORGANIC", "เกษตรอินทรีย์ (Organic)"
    HERBAL = "HERBAL", "สมุนไพรพื้นบ้าน (Herbal)"
    VEGAN = "VEGAN", "มังสวิรัติ/เจ (Vegan)"


class FoodMenu(models.Model):
    """A healthy dining menu offered by a RESTAURANT_OWNER."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="food_menus",
    )
    name = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    wellness_category = models.CharField(
        max_length=50, choices=FoodWellnessCategory.choices, default=FoodWellnessCategory.ORGANIC
    )
    calorie_estimate = models.PositiveIntegerField(null=True, blank=True)
    image = models.ImageField(upload_to=service_image_path, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "food_menus"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} - ฿{self.price} ({self.get_wellness_category_display()})"


class WellnessService(models.Model):
    """A wellness/spa treatment offered by a WELLNESS_OWNER."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="wellness_services",
    )
    name = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    duration_minutes = models.PositiveIntegerField(default=60)
    image = models.ImageField(upload_to=service_image_path, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wellness_services"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.duration_minutes} นาที) - ฿{self.price}"


class WellnessTimeSlot(models.Model):
    """
    Capacity-controlled time slot for wellness sessions.
    capacity_available is what checkout locks with select_for_update().
    """
    id = models.BigAutoField(primary_key=True)
    service = models.ForeignKey(
        WellnessService, on_delete=models.CASCADE, related_name="time_slots"
    )
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity_total = models.PositiveIntegerField(default=1)
    capacity_available = models.PositiveIntegerField(default=1)
    is_available = models.BooleanField(default=True)

    class Meta:
        db_table = "wellness_time_slots"
        ordering = ("date", "start_time")
        indexes = [
            models.Index(fields=["service", "date"]),
        ]

    def __str__(self):
        return f"{self.service.name} [{self.date} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}] ({self.capacity_available} left)"
