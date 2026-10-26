import uuid
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from .managers import UserManager


class UserRoles(models.TextChoices):
    TOURIST = "TOURIST", "Tourist (นักท่องเที่ยว)"
    HOMESTAY_OWNER = "HOMESTAY_OWNER", "Homestay Owner (เจ้าของที่พัก/โฮมสเตย์)"
    RESTAURANT_OWNER = "RESTAURANT_OWNER", "Restaurant Owner (เจ้าของร้านอาหารสุขภาพ)"
    WELLNESS_OWNER = "WELLNESS_OWNER", "Wellness Owner (เจ้าของสปา/นวดแผนไทย)"
    OTOP_OWNER = "OTOP_OWNER", "OTOP Owner (เจ้าของสินค้าชุมชน OTOP)"
    COMMUNITY_ADMIN = "COMMUNITY_ADMIN", "Community Admin (ผู้ดูแลระบบชุมชน)"
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin (ผู้ดูแลระบบสูงสุด)"


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True, default="", db_index=True)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", null=True, blank=True)

    role = models.CharField(
        max_length=30, choices=UserRoles.choices, default=UserRoles.TOURIST, db_index=True
    )
    
    # Security & Verification
    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=64, blank=True, default="")
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Django admin/staff flags
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_merchant(self):
        return self.role in {
            UserRoles.HOMESTAY_OWNER,
            UserRoles.RESTAURANT_OWNER,
            UserRoles.WELLNESS_OWNER,
            UserRoles.OTOP_OWNER,
        }

    @property
    def is_community_admin(self):
        return self.role in {UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN}


class AuditLog(models.Model):
    """
    AuditLog model for recording all critical/sensitive operations.
    Meets Non-negotiable security requirement #8 (90-day retention).
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, db_index=True)  # LOGIN, LOGOUT, CREATE, UPDATE, DELETE, LOCKOUT
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["user", "action"]),
        ]

    def __str__(self):
        actor = self.user.email if self.user else "Anonymous"
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {actor} - {self.action} on {self.model_name}:{self.object_id}"
