from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .models import HealthProfile
from .services import process_dual_ai_recommendation, calculate_bmi, calculate_bmr


@require_http_methods(["GET"])
def assessment_view(request):
    """
    Renders the interactive AI Wellness Assessment page.
    Includes real-time Alpine.js BMI/BMR feedback meters.
    """
    existing_profile = None
    if request.user.is_authenticated:
        existing_profile = HealthProfile.objects.filter(user=request.user).first()

    context = {
        "page_title": "AI Wellness Assistant - วิเคราะห์สุขภาพและวางแผนทริป",
        "profile": existing_profile,
    }
    return render(request, "ai_recommendations/assessment.html", context)


@require_http_methods(["POST"])
def assess_htmx_view(request):
    """
    HTMX Endpoint: Processes health metrics, calls Dual-AI pipeline,
    and returns tailored itinerary partial HTML for instant DOM swap.
    """
    try:
        weight_kg = float(request.POST.get("weight_kg", 0))
        height_cm = float(request.POST.get("height_cm", 0))
        age = int(request.POST.get("age", 30))
        gender = request.POST.get("gender", "other")
        health_goal = request.POST.get("health_goal", "STRESS_RELIEF")
        lifestyle = request.POST.get("lifestyle", "")
        dietary_restrictions = request.POST.getlist("dietary_restrictions")
    except (ValueError, TypeError) as exc:
        return HttpResponseBadRequest("ข้อมูลสุขภาพที่ส่งมาไม่ถูกต้อง")

    if weight_kg <= 20 or weight_kg >= 300 or height_cm <= 50 or height_cm >= 250:
        return HttpResponseBadRequest("ค่าน้ำหนักหรือส่วนสูงไม่อยู่ในเกณฑ์ที่เป็นไปได้")

    input_data = {
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "age": age,
        "gender": gender,
        "health_goal": health_goal,
        "lifestyle": lifestyle,
        "dietary_restrictions": dietary_restrictions,
    }

    result = process_dual_ai_recommendation(request.user, input_data)

    context = {
        "result": result,
    }
    return render(request, "ai_recommendations/partials/recommendation_result.html", context)
