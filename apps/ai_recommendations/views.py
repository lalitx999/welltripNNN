from datetime import timedelta

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import AIRecommendationLog, HealthProfile
from .services import start_recommendation

SESSION_KEY = "ai_recommendation_ids"
# A job still PENDING after this is treated as lost (worker down or crashed)
JOB_TIMEOUT = timedelta(minutes=3)


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
    HTMX Endpoint: validates health metrics, queues the AI job and returns a
    partial that polls result_htmx_view until the worker finishes.
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

    log = start_recommendation(request.user, input_data)

    # Guests have no user on the log, so the session proves who may poll it
    owned = request.session.get(SESSION_KEY, [])
    request.session[SESSION_KEY] = (owned + [str(log.id)])[-10:]

    log.refresh_from_db(fields=["status", "result"])
    return _render_job(request, log)


@require_http_methods(["GET"])
def result_htmx_view(request, log_id):
    """HTMX polling endpoint for a queued AI recommendation."""
    log = get_object_or_404(AIRecommendationLog, id=log_id)
    is_owner = request.user.is_authenticated and log.user_id == request.user.id
    if not is_owner and str(log.id) not in request.session.get(SESSION_KEY, []):
        raise Http404
    return _render_job(request, log)


def _render_job(request, log):
    if log.status == AIRecommendationLog.Status.DONE:
        return render(request, "ai_recommendations/partials/recommendation_result.html", {"result": log.result})
    timed_out = timezone.now() - log.created_at > JOB_TIMEOUT
    if log.status == AIRecommendationLog.Status.FAILED or timed_out:
        return render(request, "ai_recommendations/partials/recommendation_failed.html")
    return render(request, "ai_recommendations/partials/recommendation_pending.html", {"log": log})
