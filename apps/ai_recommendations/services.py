"""
Dual-AI Wellness Recommendation Engine (DeepSeek + Sisaket Catalog Matching).
1. BMI & BMR Mathematical Modeling (Mifflin-St Jeor Formula).
2. DeepSeek AI Health Rationale & Lifestyle Analysis.
3. Sisaket Eco-Tourism Catalog Matching (Accommodations, Low-Sodium Menus, Herbal Spas, OTOP Crafts).
4. Strict Medical Disclaimer (Zero diagnosis guarantee).
"""
import json
import logging
from decimal import Decimal
import requests
from django.conf import settings
from django.utils import timezone

from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, FoodWellnessCategory, WellnessService
from apps.otop.models import OTOPProduct
from .models import HealthProfile, AIRecommendationLog

logger = logging.getLogger(__name__)


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Body Mass Index: weight (kg) / [height (m)]^2."""
    if height_cm <= 0 or weight_kg <= 0:
        return 0.0
    height_m = height_cm / 100.0
    return round(weight_kg / (height_m * height_m), 2)


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> int:
    """Basal Metabolic Rate via Mifflin-St Jeor Formula."""
    if height_cm <= 0 or weight_kg <= 0 or age <= 0:
        return 1500
    if gender.lower() == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    return int(round(bmr))


def get_bmi_category(bmi: float) -> str:
    if bmi < 18.5:
        return "น้ำหนักน้อยกว่าเกณฑ์ (Underweight)"
    elif bmi < 23.0:
        return "สมส่วนตามเกณฑ์เอเชีย (Normal Weight)"
    elif bmi < 25.0:
        return "น้ำหนักเกินเกณฑ์ (Overweight)"
    elif bmi < 30.0:
        return "โรคอ้วนระดับ 1 (Obese Class I)"
    else:
        return "โรคอ้วนระดับ 2 (Obese Class II)"


def analyze_health_deepseek(profile_data: dict) -> str:
    """Stage 1: DeepSeek AI Engine - Health Rationale & Wellness Guidance."""
    api_key = getattr(settings, "DEEPSEEK_API_KEY", "") or ""
    bmi = profile_data.get("bmi", 22.0)
    goal = profile_data.get("health_goal", "STRESS_RELIEF")
    diet = ", ".join(profile_data.get("dietary_restrictions", [])) or "ไม่มี"
    age = profile_data.get("age", 30)

    if api_key:
        try:
            prompt = (
                f"คุณคือผู้เชี่ยวชาญด้านสุขภาพและการท่องเที่ยวเชิงส่งเสริมสุขภาพ (Wellness Tourism)\n"
                f"ข้อมูลนักท่องเที่ยว: น้ำหนัก {profile_data.get('weight_kg')} kg, ส่วนสูง {profile_data.get('height_cm')} cm, "
                f"BMI {bmi} ({get_bmi_category(bmi)}), BMR {profile_data.get('bmr')} kcal, เพศ {profile_data.get('gender')}, อายุ {age} ปี\n"
                f"เป้าหมายสุขภาพ: {goal}, ข้อจำกัดทางอาหาร: {diet}\n"
                f"โปรดวิเคราะห์สภาวะสุขภาพสั้นๆ 3-4 ประโยค และแนะนำกิจกรรมผ่อนคลายในวิถีธรรมชาติและสมุนไพรพื้นถิ่นอีสานใต้ (ศรีสะเกษ) "
                f"ห้ามวินิจฉัยโรคหรืออ้างผลการรักษาเด็ดขาด"
            )
            req_data = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=req_data,
                timeout=12,
            )
            if resp.status_code == 200:
                res_json = resp.json()
                return res_json["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("DeepSeek API call failed, falling back to expert rule engine: %s", exc)

    # Deterministic Expert Rule Engine Fallback
    bmi_label = get_bmi_category(bmi)
    if "STRESS" in goal.upper():
        advice = "เน้นการฟื้นฟูระบบประสาทและคลายความตึงเครียดของกล้ามเนื้อด้วยการแช่อบไอน้ำสมุนไพรสดและการพักผ่อนริมลำธารธรรมชาติเพื่อปรับสมดุลคลื่นสมอง"
    elif "WEIGHT" in goal.upper() or bmi >= 25.0:
        advice = "เน้นอาหารสุขภาพที่ให้พลังงานไม่เกินอัตรา BMR ลดโซเดียมและน้ำตาล ควบคู่กับการเดินสำรวจวิถีสวนเกษตรอินทรีย์เพื่อกระตุ้นระบบเผาผลาญ"
    elif "DETOX" in goal.upper():
        advice = "เน้นเมนูผักอินทรีย์ดินภูเขาไฟที่มีสารต้านอนุมูลอิสระสูง และการนวดกดจุดระบายน้ำเหลืองด้วยลูกประคบสมุนไพรศรีสะเกษ"
    else:
        advice = "เน้นการพักผ่อนอย่างมีสุขภาวะ สัมผัสวิถีชีวิตชาวสวนและการรับประทานอาหารปรุงสุกสะอาดจากวัตถุดิบปลอดสารเคมี 100%"

    return (
        f"นักท่องเที่ยวมีค่า BMI อยู่ที่ {bmi} จัดอยู่ในเกณฑ์ '{bmi_label}' "
        f"มีอัตราการเผาผลาญพื้นฐาน (BMR) ประมาณ {profile_data.get('bmr')} กิโลแคลอรี/วัน "
        f"สำหรับเป้าหมายด้านสุขภาวะที่ระบุ: {advice}"
    )


def match_sisaket_wellness_package(health_analysis: str, profile_data: dict) -> dict:
    """Stage 2: Match actual Sisaket Database Catalog to Tourist Health Profile."""
    goal = profile_data.get("health_goal", "STRESS_RELIEF")
    dietary = profile_data.get("dietary_restrictions", [])

    # 1. Accommodations
    accommodations = Accommodation.objects.filter(
        status=AccommodationStatus.ACTIVE
    ).prefetch_related("rooms")[:2]

    package_items = []
    total_price = Decimal("0.00")

    for acc in accommodations:
        active_rooms = acc.rooms.filter(is_active=True).order_by("base_price_per_night")
        if active_rooms.exists():
            room = active_rooms.first()
            total_price += room.base_price_per_night
            package_items.append({
                "item_type": "ACCOMMODATION",
                "entity_id": str(room.id),
                "title": f"{acc.name} - {room.name}",
                "unit_price": room.base_price_per_night,
                "quantity": 1,
                "category_label": f"โฮมสเตย์ธรรมชาติ ({room.capacity_people} ท่าน)",
                "detail_url": f"/accommodations/{acc.slug}/",
            })
            break

    # 2. Healthy Food Menus
    food_qs = FoodMenu.objects.filter(is_available=True)
    if "LOW_SODIUM" in dietary:
        food_qs = food_qs.filter(wellness_category=FoodWellnessCategory.LOW_SODIUM)
    elif "ORGANIC" in dietary:
        food_qs = food_qs.filter(wellness_category=FoodWellnessCategory.ORGANIC)

    if not food_qs.exists():
        food_qs = FoodMenu.objects.filter(is_available=True)

    for food in food_qs[:2]:
        total_price += food.price
        package_items.append({
            "item_type": "FOOD",
            "entity_id": str(food.id),
            "title": food.name,
            "unit_price": food.price,
            "quantity": 1,
            "category_label": f"อาหารสุขภาพ ({food.get_wellness_category_display()}) ~{food.calorie_estimate or 250} kcal",
            "detail_url": "/services/",
        })

    # 3. Wellness Treatment
    wellness_qs = WellnessService.objects.filter(is_active=True)
    for service in wellness_qs[:1]:
        total_price += service.price
        package_items.append({
            "item_type": "WELLNESS",
            "entity_id": str(service.id),
            "title": service.name,
            "unit_price": service.price,
            "quantity": 1,
            "category_label": f"สปา & นวดแผนไทย ({service.duration_minutes} นาที)",
            "detail_url": "/services/",
        })

    # 4. OTOP Product
    otop_qs = OTOPProduct.objects.filter(is_active=True, stock_quantity__gt=0)
    for prod in otop_qs[:1]:
        total_price += prod.price
        package_items.append({
            "item_type": "OTOP",
            "entity_id": str(prod.id),
            "title": prod.name,
            "unit_price": prod.price,
            "quantity": 1,
            "category_label": f"สินค้าชุมชน ({prod.get_category_display()})",
            "detail_url": "/otop/",
        })

    return {
        "package_title": "ทริปสุขภาวะและวิถีธรรมชาติขุนหาญ-กันทรลักษ์ (2 วัน 1 คืน)",
        "duration_label": "2 วัน 1 คืน (พักผ่อนเชิงส่งเสริมสุขภาวะ)",
        "total_package_price": total_price,
        "items": package_items,
        "disclaimer": (
            "ข้อควรทราบ: ผลวิเคราะห์และข้อเสนอแนะนี้จัดทำขึ้นเพื่อการท่องเที่ยวเชิงส่งเสริมสุขภาพ (Wellness Tourism) "
            "เท่านั้น ไม่สามารถใช้ทดแทนคำแนะนำ การวินิจฉัย หรือการรักษาทางการแพทย์จากแพทย์ผู้เชี่ยวชาญได้"
        ),
    }


def process_dual_ai_recommendation(user, input_data: dict) -> dict:
    """Full Pipeline: Validation -> Math Modeling -> AI Reasoning -> Catalog Matching -> Audit Log."""
    weight = float(input_data["weight_kg"])
    height = float(input_data["height_cm"])
    age = int(input_data.get("age", 30))
    gender = str(input_data.get("gender", "other"))
    goal = str(input_data["health_goal"])
    lifestyle = str(input_data.get("lifestyle", ""))
    dietary = input_data.get("dietary_restrictions", [])

    bmi = calculate_bmi(weight, height)
    bmr = calculate_bmr(weight, height, age, gender)

    profile_dict = {
        "weight_kg": weight,
        "height_cm": height,
        "bmi": bmi,
        "bmr": bmr,
        "gender": gender,
        "age": age,
        "health_goal": goal,
        "lifestyle": lifestyle,
        "dietary_restrictions": dietary,
    }

    # Persist or update profile if user is logged in
    if user and user.is_authenticated:
        HealthProfile.objects.update_or_create(
            user=user,
            defaults={
                "weight_kg": Decimal(str(weight)),
                "height_cm": Decimal(str(height)),
                "bmi": Decimal(str(bmi)),
                "bmr": bmr,
                "gender": gender,
                "age": age,
                "health_goal": goal,
                "lifestyle": lifestyle,
                "dietary_restrictions": dietary,
            },
        )

    # 1. DeepSeek AI Health Reasoning
    health_analysis = analyze_health_deepseek(profile_dict)

    # 2. Sisaket Catalog Matching
    package_result = match_sisaket_wellness_package(health_analysis, profile_dict)

    # 3. Log to DB
    AIRecommendationLog.objects.create(
        user=user if user and user.is_authenticated else None,
        input_snapshot=profile_dict,
        health_analysis=health_analysis,
        recommended_package={
            "package_title": package_result["package_title"],
            "total_package_price": str(package_result["total_package_price"]),
            "items_count": len(package_result["items"]),
        },
    )

    return {
        "health_metrics": {
            "bmi": str(bmi),
            "bmi_category": get_bmi_category(bmi),
            "bmr": bmr,
            "weight_kg": weight,
            "height_cm": height,
            "health_goal": goal,
        },
        "deepseek_analysis": health_analysis,
        "recommended_package": package_result,
    }
