import uuid
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from .managers import UserManager
from .banks import ThaiBank
from django.utils.translation import gettext_lazy


class UserRoles(models.TextChoices):
    TOURIST = "TOURIST", gettext_lazy("Tourist (นักท่องเที่ยว)")
    HOMESTAY_OWNER = "HOMESTAY_OWNER", gettext_lazy("Homestay Owner (เจ้าของที่พัก/โฮมสเตย์)")
    RESTAURANT_OWNER = "RESTAURANT_OWNER", gettext_lazy("Restaurant Owner (เจ้าของร้านอาหารสุขภาพ)")
    WELLNESS_OWNER = "WELLNESS_OWNER", gettext_lazy("Wellness Owner (เจ้าของสปา/นวดแผนไทย)")
    OTOP_OWNER = "OTOP_OWNER", gettext_lazy("OTOP Owner (เจ้าของสินค้าชุมชน OTOP)")
    COMMUNITY_ADMIN = "COMMUNITY_ADMIN", gettext_lazy("Community Admin (ผู้ดูแลระบบชุมชน)")
    SUPER_ADMIN = "SUPER_ADMIN", gettext_lazy("Super Admin (ผู้ดูแลระบบสูงสุด)")


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
    # Set on self-registration only, so accounts from before OTP keep logging in
    email_verification_required = models.BooleanField(default=False)
    # Google's stable account ID; unlike the email it never changes or gets recycled
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
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
    def display_name(self):
        """
        Public-facing name (shop name for partners). Never the email address:
        that would publish a personal contact on every product and room page.
        """
        if self.is_superuser or self.role in (UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN):
            return "WellTrip Sisaket"  # items the platform sells itself
        profile = getattr(self, "merchant_profile", None)
        if profile and profile.business_name and "@" not in profile.business_name:
            return profile.business_name
        name = f"{self.first_name} {self.last_name}".strip()
        if name and "@" not in name:
            return name
        return gettext_lazy("ผู้ประกอบการชุมชน") if self.is_merchant else gettext_lazy("สมาชิก WellTrip")

    @property
    def needs_email_verification(self):
        return self.email_verification_required and not self.email_verified

    @property
    def is_merchant(self):
        return self.role in {
            UserRoles.HOMESTAY_OWNER,
            UserRoles.RESTAURANT_OWNER,
            UserRoles.WELLNESS_OWNER,
            UserRoles.OTOP_OWNER,
        }

    @property
    def service_roles(self):
        """
        The user's role plus the partner roles of every extra service their shop opened.
        A homestay owner who opened OTOP counts as an OTOP owner in Partner Studio.
        """
        roles = {self.role}
        if self.is_merchant:
            profile = getattr(self, "merchant_profile", None)
            if profile is not None:
                roles.update(CATEGORY_ROLES[c] for c in profile.service_categories if c in CATEGORY_ROLES)
        return roles

    def has_service_role(self, role):
        return role in self.service_roles

    # Template-friendly checks for the Partner Studio menu (admins are checked separately)
    @property
    def manages_homestay(self):
        return self.has_service_role(UserRoles.HOMESTAY_OWNER)

    @property
    def manages_restaurant(self):
        return self.has_service_role(UserRoles.RESTAURANT_OWNER)

    @property
    def manages_wellness(self):
        return self.has_service_role(UserRoles.WELLNESS_OWNER)

    @property
    def manages_otop(self):
        return self.has_service_role(UserRoles.OTOP_OWNER)

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


class EmailVerificationOTP(models.Model):
    """Temporary 6-digit OTP code sent to user email for verification."""
    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(db_index=True)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=50, default="MERCHANT_REGISTER")
    is_used = models.BooleanField(default=False)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "email_verification_otps"
        ordering = ("-created_at",)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

    def __str__(self):
        return f"OTP for {self.email} ({self.otp_code}) - Used: {self.is_used}"


SERVICE_CATEGORY_CHOICES = [
    ("HOMESTAY", gettext_lazy("โฮมสเตย์ / ที่พักชุมชน")),
    ("RESTAURANT", gettext_lazy("ร้านอาหารเพื่อสุขภาพ")),
    ("WELLNESS", gettext_lazy("บริการสุขภาพ & สปา")),
    ("OTOP", gettext_lazy("สินค้า OTOP ชุมชน")),
]

# Which partner role a shop category grants in Partner Studio
CATEGORY_ROLES = {
    "HOMESTAY": UserRoles.HOMESTAY_OWNER,
    "RESTAURANT": UserRoles.RESTAURANT_OWNER,
    "WELLNESS": UserRoles.WELLNESS_OWNER,
    "OTOP": UserRoles.OTOP_OWNER,
}


class MerchantApprovalStatus(models.TextChoices):
    PENDING = "PENDING", gettext_lazy("อยู่ระหว่างการตรวจสอบ (Pending Review)")
    APPROVED = "APPROVED", gettext_lazy("อนุมัติแล้ว (Approved)")
    REJECTED = "REJECTED", gettext_lazy("ไม่ผ่านการอนุมัติ (Rejected)")


class MerchantProfile(models.Model):
    """Store rich shop / vendor registration details for onboarding & approval."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="merchant_profile",
    )
    business_name = models.CharField(max_length=200)
    business_category = models.CharField(
        max_length=50,
        choices=SERVICE_CATEGORY_CHOICES,
        default="HOMESTAY",
    )
    description = models.TextField(blank=True, default="")
    google_maps_url = models.URLField(max_length=500, blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    opening_hours = models.CharField(
        max_length=150, blank=True, default="08:00 - 18:00 น."
    )
    cover_image_url = models.TextField(blank=True, default="")
    # Other kinds of business the partner runs on top of business_category, e.g. a
    # homestay that also sells OTOP goods. Category codes; open without admin approval.
    extra_services = models.JSONField(default=list, blank=True)

    # Where the admin transfers the partner's share after settling the books.
    # Only the partner and platform admins ever see these.
    payout_bank = models.CharField(max_length=20, choices=ThaiBank.choices, blank=True, default="")
    payout_account_number = models.CharField(max_length=20, blank=True, default="")
    payout_account_name = models.CharField(max_length=200, blank=True, default="")
    promptpay_id = models.CharField(max_length=13, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=MerchantApprovalStatus.choices,
        default=MerchantApprovalStatus.PENDING,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_profiles"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.business_name} ({self.status}) - {self.user.email}"

    @property
    def is_public(self):
        """The storefront page is visible only once an admin approved the shop."""
        return self.status == MerchantApprovalStatus.APPROVED

    @property
    def service_categories(self):
        """The main category first, then every valid extra one (no duplicates)."""
        cats = [self.business_category]
        for code in self.extra_services or []:
            if code in CATEGORY_ROLES and code not in cats:
                cats.append(code)
        return cats

    @property
    def extra_service_labels(self):
        labels = dict(SERVICE_CATEGORY_CHOICES)
        return [labels[c] for c in self.service_categories[1:]]

    @property
    def has_payout_account(self):
        return bool(self.payout_bank and self.payout_account_number and self.payout_account_name)


def shop_image_path(instance, filename):
    from apps.core.services.media import secure_upload_path
    return secure_upload_path(instance, filename, model_subdir="shops")


class MerchantShopImage(models.Model):
    """Storefront photos a partner sets up (also while waiting for approval). At most 3 per shop."""
    MAX_PER_SHOP = 3

    id = models.BigAutoField(primary_key=True)
    profile = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="shop_images")
    image = models.ImageField(upload_to=shop_image_path)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_shop_images"
        ordering = ("order", "id")

    def __str__(self):
        return f"Shop image {self.order} of {self.profile.business_name}"


