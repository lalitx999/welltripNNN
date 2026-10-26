import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from apps.core.services.media import secure_upload_path


def otop_image_path(instance, filename):
    return secure_upload_path(instance, filename, model_subdir="otop")


class OTOPCategory(models.TextChoices):
    HERBAL_PRODUCT = "HERBAL_PRODUCT", "สมุนไพรและผลิตภัณฑ์สุขภาพ"
    TEXTILE = "TEXTILE", "ผ้าไหม ผ้าฝ้าย และเครื่องแต่งกาย"
    PROCESSED_FOOD = "PROCESSED_FOOD", "อาหารแปรรูปและของฝาก"
    CRAFT = "CRAFT", "หัตถกรรม งานจักสาน และของแต่งบ้าน"


class OTOPProduct(models.Model):
    """
    OTOP Retail domain model offered by an OTOP_OWNER.
    stock_quantity is a PositiveIntegerField which adds a CHECK (>= 0) constraint
    at the database layer, guaranteeing inventory can never go negative.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="otop_products",
    )
    name = models.CharField(max_length=200, db_index=True)
    category = models.CharField(
        max_length=50, choices=OTOPCategory.choices, default=OTOPCategory.HERBAL_PRODUCT
    )
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock_quantity = models.PositiveIntegerField(
        default=0,
        help_text="จำนวนสินค้าคงคลัง (ห้ามติดลบเด็ดขาดตามระดับฐานข้อมูล)"
    )
    image = models.ImageField(upload_to=otop_image_path, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "otop_products"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} - ฿{self.price} (คงเหลือ {self.stock_quantity})"
