from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, UserRoles
from apps.accommodations.models import Accommodation, Room, AccommodationStatus
from apps.services.models import FoodMenu, FoodWellnessCategory, WellnessService
from apps.otop.models import OTOPProduct, OTOPCategory
from .models import HealthProfile, AIRecommendationLog
from .services import calculate_bmi, calculate_bmr, get_bmi_category, process_dual_ai_recommendation


class AIRecommendationsTestCase(TestCase):
    """
    Test suite for Dual-AI Wellness Recommendation Engine (EP 11).
    Verifies mathematical modeling, catalog matching, and HTMX endpoints.
    """

    def setUp(self):
        self.client = Client()
        self.tourist = User.objects.create_user(
            email="tourist.ai@example.com",
            password="SecurePassword123!",
            first_name="ปรีชา",
            last_name="สุขใจ",
            role=UserRoles.TOURIST,
        )
        self.merchant = User.objects.create_user(
            email="merchant.ai@example.com",
            password="SecurePassword123!",
            role=UserRoles.HOMESTAY_OWNER,
        )

        # Seed test catalog
        self.acc = Accommodation.objects.create(
            owner=self.merchant,
            name="บ้านสวนริมธาร ขุนหาญ",
            status=AccommodationStatus.ACTIVE,
        )
        self.room = Room.objects.create(
            accommodation=self.acc,
            name="เรือนริมธาร",
            base_price_per_night=Decimal("1200.00"),
            total_rooms_count=2,
            is_active=True,
        )
        self.food = FoodMenu.objects.create(
            owner=self.merchant,
            name="แกงอ่อมปลาคังโซเดียมต่ำ",
            price=Decimal("180.00"),
            wellness_category=FoodWellnessCategory.LOW_SODIUM,
            calorie_estimate=280,
            is_available=True,
        )
        self.service = WellnessService.objects.create(
            owner=self.merchant,
            name="นวดประคบสมุนไพรสด",
            price=Decimal("650.00"),
            duration_minutes=90,
            is_active=True,
        )
        self.otop = OTOPProduct.objects.create(
            owner=self.merchant,
            name="หอมแดงศรีสะเกษ GI",
            price=Decimal("190.00"),
            stock_quantity=50,
            is_active=True,
        )

    def test_bmi_and_bmr_calculation_math(self):
        """Verifies mathematical accuracy of BMI and Mifflin-St Jeor BMR."""
        # 70 kg, 175 cm -> BMI = 70 / (1.75^2) = 22.86
        bmi = calculate_bmi(70, 175)
        self.assertEqual(bmi, 22.86)
        self.assertEqual(get_bmi_category(bmi), "สมส่วนตามเกณฑ์เอเชีย (Normal Weight)")

        # Male: 70kg, 175cm, 30yo -> 10*70 + 6.25*175 - 5*30 + 5 = 700 + 1093.75 - 150 + 5 = 1648.75 -> 1649
        bmr_male = calculate_bmr(70, 175, 30, "male")
        self.assertEqual(bmr_male, 1649)

        # Female: 55kg, 160cm, 25yo -> 10*55 + 6.25*160 - 5*25 - 161 = 550 + 1000 - 125 - 161 = 1264
        bmr_female = calculate_bmr(55, 160, 25, "female")
        self.assertEqual(bmr_female, 1264)

    def test_process_dual_ai_recommendation_pipeline(self):
        """Verifies full AI pipeline, catalog matching and database logging."""
        input_data = {
            "weight_kg": 68.0,
            "height_cm": 172.0,
            "age": 32,
            "gender": "male",
            "health_goal": "STRESS_RELIEF",
            "lifestyle": "ทำงานหน้าจอคอมพิวเตอร์วันละ 8-10 ชั่วโมง",
            "dietary_restrictions": ["LOW_SODIUM"],
        }

        result = process_dual_ai_recommendation(self.tourist, input_data)

        self.assertIn("health_metrics", result)
        self.assertIn("deepseek_analysis", result)
        self.assertIn("recommended_package", result)

        package = result["recommended_package"]
        self.assertGreater(len(package["items"]), 0)
        self.assertGreater(package["total_package_price"], Decimal("0.00"))

        # Verify DB logging
        log_entry = AIRecommendationLog.objects.filter(user=self.tourist).first()
        self.assertIsNotNone(log_entry)

        profile = HealthProfile.objects.filter(user=self.tourist).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.weight_kg, Decimal("68.0"))

    def test_assessment_view_renders(self):
        """GET /ai/ renders assessment form with 200 OK."""
        response = self.client.get(reverse("ai_recommendations:assessment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ข้อมูลร่างกายและเป้าหมาย")
        self.assertContains(response, "x-data")

    def test_assess_htmx_view_returns_partial_html(self):
        """POST /ai/assess/ with valid payload returns rendered partial HTML."""
        self.client.force_login(self.tourist)
        payload = {
            "weight_kg": 60,
            "height_cm": 165,
            "age": 28,
            "gender": "female",
            "health_goal": "DETOX",
            "dietary_restrictions": ["ORGANIC"],
        }
        response = self.client.post(reverse("ai_recommendations:assess_htmx"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ผลวิเคราะห์สุขภาพเฉพาะบุคคล")
        self.assertContains(response, "Tailored Itinerary")

    def test_assess_htmx_view_rejects_invalid_inputs(self):
        """Rejects impossible weight/height values with 400 Bad Request."""
        payload = {
            "weight_kg": 5,  # Too light
            "height_cm": 165,
        }
        response = self.client.post(reverse("ai_recommendations:assess_htmx"), payload)
        self.assertEqual(response.status_code, 400)
