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
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, FoodWellnessCategory, WellnessService
from apps.otop.models import OTOPProduct
from .bmi_advice import bmi_advice
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
                "model": settings.DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }
            resp = requests.post(
                f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",
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


GOAL_LABELS = {
    "STRESS_RELIEF": "คลายเครียด",
    "DETOX": "ดีท็อกซ์",
    "WEIGHT_MANAGEMENT": "ควบคุมน้ำหนัก",
    "SENIOR_WELLNESS": "ผู้สูงอายุ",
}
MAX_PLACES = 5


def _normalize_place(name: str) -> str:
    import re
    return re.sub(r"[\s\-–—()\[\]\"'“”.,:]", "", (name or "").lower())


def _match_attraction(name, attractions):
    """The published attraction this AI-suggested name refers to, if any."""
    key = _normalize_place(name)
    if len(key) < 3:
        return None
    for entry in attractions:
        title = _normalize_place(entry.title)
        if title and (key in title or title in key):
            return entry
    return None


def _ask_deepseek_for_places(profile_data: dict):
    """DeepSeek's list of places/activities in Sisaket for this visitor, or None when unavailable."""
    api_key = getattr(settings, "DEEPSEEK_API_KEY", "") or ""
    if not api_key:
        return None
    goal = GOAL_LABELS.get(str(profile_data.get("health_goal")), str(profile_data.get("health_goal", "")))
    prompt = (
        "คุณคือไกด์ท้องถิ่นจังหวัดศรีสะเกษ ประเทศไทย ที่รู้จักแหล่งท่องเที่ยวจริงในจังหวัด\n"
        f"นักท่องเที่ยวอายุ {profile_data.get('age')} ปี BMI {profile_data.get('bmi')} "
        f"({get_bmi_category(float(profile_data.get('bmi') or 0))}) เป้าหมาย: {goal}\n"
        f"แนะนำสถานที่ท่องเที่ยวหรือกิจกรรมที่มีอยู่จริงในจังหวัดศรีสะเกษ {MAX_PLACES} แห่ง ที่เหมาะกับสุขภาพและเป้าหมายนี้ "
        "เช่น วัด ปราสาท อุทยาน น้ำตก ตลาด สวนเกษตร กิจกรรมชุมชน ห้ามแต่งชื่อสถานที่ขึ้นเอง\n"
        "ตอบเป็น JSON array เท่านั้น ไม่มีข้อความอื่น แต่ละรายการมี key: "
        '"name" (ชื่อสถานที่ภาษาไทย), "district" (อำเภอ), "reason" (เหตุผลสั้นๆ 1 ประโยคว่าทำไมเหมาะกับสุขภาพของเขา)'
    )
    try:
        resp = requests.post(
            f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            json={"model": settings.DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        text = resp.json()["choices"][0]["message"]["content"].strip()
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return None
        rows = json.loads(text[start:end + 1])
    except Exception as exc:
        logger.warning("DeepSeek place suggestions failed: %s", exc)
        return None
    places = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not str(row.get("name", "")).strip():
            continue
        places.append({
            "name": str(row.get("name", "")).strip()[:120],
            "district": str(row.get("district", "")).strip()[:60],
            "reason": str(row.get("reason", "")).strip()[:300],
        })
    return places[:MAX_PLACES] or None


def suggest_sisaket_places(profile_data: dict) -> list:
    """
    Places and activities in Sisaket for this visitor. DeepSeek may suggest places
    the site does not list yet; a suggestion that matches a published attraction
    links to its page, the others are marked as AI suggestions to check before going.
    Without the AI, published attractions are offered instead.
    """
    from django.urls import reverse
    from apps.core.selectors.catalog_selector import published_attractions

    attractions = list(published_attractions().order_by("title"))
    places = []
    for row in _ask_deepseek_for_places(profile_data) or []:
        entry = _match_attraction(row["name"], attractions)
        places.append({
            **row,
            "source": "AI",
            "verified": entry is not None,
            "url": reverse("community:story_detail", args=[entry.id]) if entry else "",
            "image_url": entry.display_image_url if entry else "",
        })
    if not places:
        for entry in attractions[:4]:
            places.append({
                "name": entry.title,
                "district": entry.location.replace(" จ.ศรีสะเกษ", ""),
                "reason": (entry.summary or "")[:200],
                "source": "WELLTRIP",
                "verified": True,
                "url": reverse("community:story_detail", args=[entry.id]),
                "image_url": entry.display_image_url,
            })
    return places


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
            total_price += room.customer_price
            package_items.append({
                "item_type": "ACCOMMODATION",
                "entity_id": str(room.id),
                "title": f"{acc.name} - {room.name}",
                "unit_price": room.customer_price,
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
        total_price += food.customer_price
        package_items.append({
            "item_type": "FOOD",
            "entity_id": str(food.id),
            "title": food.name,
            "unit_price": food.customer_price,
            "quantity": 1,
            "category_label": f"อาหารสุขภาพ ({food.get_wellness_category_display()}) ~{food.calorie_estimate or 250} kcal",
            "detail_url": f"/services/detail/food/{food.id}/",
        })

    # 3. Wellness Treatment
    wellness_qs = WellnessService.objects.filter(is_active=True)
    for service in wellness_qs[:1]:
        total_price += service.customer_price
        package_items.append({
            "item_type": "WELLNESS",
            "entity_id": str(service.id),
            "title": service.name,
            "unit_price": service.customer_price,
            "quantity": 1,
            "category_label": f"สปา & นวดแผนไทย ({service.duration_minutes} นาที)",
            "detail_url": f"/services/detail/wellness/{service.id}/",
        })

    # 4. OTOP Product
    otop_qs = OTOPProduct.objects.filter(is_active=True, stock_quantity__gt=0)
    for prod in otop_qs[:1]:
        total_price += prod.customer_price
        package_items.append({
            "item_type": "OTOP",
            "entity_id": str(prod.id),
            "title": prod.name,
            "unit_price": prod.customer_price,
            "quantity": 1,
            "category_label": f"สินค้าชุมชน ({prod.get_category_display()})",
            "detail_url": f"/otop/{prod.id}/",
        })

    return {
        "package_title": "แพ็กเกจทริปสุขภาวะศรีสะเกษที่แนะนำสำหรับคุณ",
        "duration_label": "2 วัน 1 คืน (พักผ่อนเชิงส่งเสริมสุขภาวะ)",
        "total_package_price": total_price,
        "items": package_items,
        "disclaimer": (
            "ข้อควรทราบ: ผลวิเคราะห์และข้อเสนอแนะนี้จัดทำขึ้นเพื่อการท่องเที่ยวเชิงส่งเสริมสุขภาพ (Wellness Tourism) "
            "เท่านั้น ไม่สามารถใช้ทดแทนคำแนะนำ การวินิจฉัย หรือการรักษาทางการแพทย์จากแพทย์ผู้เชี่ยวชาญได้"
        ),
    }


def start_recommendation(user, input_data: dict) -> AIRecommendationLog:
    """
    Fast part, runs in the request: BMI/BMR math, save the health profile, and
    create a PENDING job. The slow AI call is queued to run_recommendation_task.
    """
    from .tasks import run_recommendation_task

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

    is_member = bool(user and user.is_authenticated)
    if is_member:
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

    log = AIRecommendationLog.objects.create(
        user=user if is_member else None,
        input_snapshot=profile_dict,
        status=AIRecommendationLog.Status.PENDING,
    )
    run_recommendation_task.delay_on_commit(str(log.id))
    return log


def complete_recommendation(log_id) -> None:
    """Slow part, runs in the Celery worker: DeepSeek call + catalog matching."""
    log = AIRecommendationLog.objects.filter(pk=log_id, status=AIRecommendationLog.Status.PENDING).first()
    if not log:
        return

    profile = log.input_snapshot
    try:
        health_analysis = analyze_health_deepseek(profile)
        package_result = match_sisaket_wellness_package(health_analysis, profile)
        places = suggest_sisaket_places(profile)
    except Exception:
        logger.exception("AI recommendation %s failed", log_id)
        log.status = AIRecommendationLog.Status.FAILED
        log.save(update_fields=["status"])
        return

    result = {
        "health_metrics": {
            "bmi": str(profile["bmi"]),
            "bmi_category": get_bmi_category(profile["bmi"]),
            "bmr": profile["bmr"],
            "weight_kg": profile["weight_kg"],
            "height_cm": profile["height_cm"],
            "health_goal": profile["health_goal"],
        },
        "deepseek_analysis": health_analysis,
        "recommended_package": package_result,
        "bmi_advice": bmi_advice(profile["bmi"]),
        "places": places,
    }
    # Decimal prices -> strings so the result fits a JSONField
    log.result = json.loads(json.dumps(result, cls=DjangoJSONEncoder))
    log.health_analysis = health_analysis
    log.recommended_package = {
        "package_title": package_result["package_title"],
        "total_package_price": str(package_result["total_package_price"]),
        "items_count": len(package_result["items"]),
    }
    log.status = AIRecommendationLog.Status.DONE
    log.save(update_fields=["result", "health_analysis", "recommended_package", "status"])
