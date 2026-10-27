import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models


class HealthProfile(models.Model):
    """
    User health and wellness profile.
    Used by Dual-AI engine to generate customized itineraries.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="health_profile",
    )
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2)
    bmi = models.DecimalField(max_digits=4, decimal_places=2)
    bmr = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=20, default="other")
    age = models.IntegerField(default=30)
    health_goal = models.CharField(max_length=100)
    lifestyle = models.CharField(max_length=100, blank=True, default="")
    dietary_restrictions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "health_profiles"
        ordering = ("-updated_at",)

    def __str__(self):
        user_str = self.user.email if self.user else "Guest"
        return f"HealthProfile ({user_str}) - BMI: {self.bmi}"


class AIRecommendationLog(models.Model):
    """
    Historical log of AI recommendation assessments and generated packages.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_recommendations",
    )
    input_snapshot = models.JSONField(default=dict)
    health_analysis = models.TextField(blank=True, default="")
    recommended_package = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_recommendation_logs"
        ordering = ("-created_at",)

    def __str__(self):
        user_str = self.user.email if self.user else "Guest"
        return f"AIRecommendation {self.id} for {user_str}"
