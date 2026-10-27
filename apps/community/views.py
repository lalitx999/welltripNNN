from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_http_methods
from django.utils import timezone

from apps.accounts.services.audit import record_audit_log
from apps.community.models import (
    MapLocation,
    PassportStamp,
    MapLocationCategory,
    UserPoints,
    Coupon,
    EditorialEntry,
    LocationEvent,
)


@require_GET
def map_view(request):
    """Interactive Sisaket Cultural & Wellness Map view."""
    category = request.GET.get('category')
    locations = MapLocation.objects.filter(is_active=True)

    if category and category in MapLocationCategory.values:
        locations = locations.filter(category=category)

    return render(request, 'community/map.html', {
        'locations': locations,
        'categories': MapLocationCategory.choices,
        'selected_category': category or 'ALL',
        'total_locations': locations.count(),
    })


@require_GET
def locations_api_view(request):
    """Returns JSON coordinates and details for Leaflet.js map markers."""
    category = request.GET.get('category')
    locations = MapLocation.objects.filter(is_active=True)

    if category and category in MapLocationCategory.values:
        locations = locations.filter(category=category)

    data = [
        {
            "id": str(loc.id),
            "title": loc.title,
            "category": loc.category,
            "category_label": loc.get_category_display(),
            "lat": float(loc.latitude),
            "lng": float(loc.longitude),
            "address": loc.address,
            "qr_secret": loc.qr_secret,
        }
        for loc in locations
    ]
    return JsonResponse({"locations": data})


@login_required
@require_GET
def passport_view(request):
    """Digital Passport book showing tourist's collected stamps, badges, and loyalty points."""
    stamps = PassportStamp.objects.filter(user=request.user).select_related('location').order_by('-stamped_at')
    stamp_count = stamps.count()

    points_obj, _ = UserPoints.objects.get_or_create(user=request.user)

    # Determine Explorer Level
    if stamp_count >= 10:
        badge = {"name": "Gold Community Ambassador", "color": "bg-gold text-forest"}
    elif stamp_count >= 5:
        badge = {"name": "Silver Cultural Explorer", "color": "bg-slate-200 text-slate-800"}
    elif stamp_count >= 1:
        badge = {"name": "Bronze Heritage Scout", "color": "bg-amber-100 text-amber-900"}
    else:
        badge = {"name": "Novice Traveler", "color": "bg-gray-100 text-gray-600"}

    all_locations = MapLocation.objects.filter(is_active=True).count()

    return render(request, 'community/passport.html', {
        'stamps': stamps,
        'stamp_count': stamp_count,
        'all_locations': all_locations,
        'badge': badge,
        'points': points_obj,
    })


@login_required
def claim_stamp_view(request, qr_secret):
    """
    Endpoint reached when tourist scans physical QR code at a venue.
    Validates QR secret, awards digital stamp, and credits loyalty points.
    """
    location = get_object_or_404(MapLocation, qr_secret=qr_secret, is_active=True)

    stamp, created = PassportStamp.objects.get_or_create(
        user=request.user,
        location=location,
    )

    if created:
        points_obj, _ = UserPoints.objects.get_or_create(user=request.user)
        points_obj.total_earned += 50
        points_obj.current_balance += 50
        points_obj.save(update_fields=["total_earned", "current_balance", "updated_at"])

        record_audit_log(
            request=request,
            action="CREATE",
            model_name="PassportStamp",
            object_id=str(stamp.id),
            changes={
                "location_title": location.title,
                "category": location.category,
                "points_awarded": 50,
            },
            user=request.user,
        )
        messages.success(request, f"ยินดีด้วย! คุณได้รับตราประทับ '{location.title}' และรับ 50 คะแนนสะสม")
    else:
        messages.info(request, f"คุณเคยได้รับตราประทับของ '{location.title}' ไปแล้ว")

    return redirect('community:passport')


# ---------------------------------------------------------------------------
# Stories & Cultural Articles (Editorial)
# ---------------------------------------------------------------------------
@require_GET
def stories_list_view(request):
    """Directory of cultural stories, local wisdom, and eco-tourism news."""
    kind = request.GET.get('kind')
    stories = EditorialEntry.objects.filter(is_published=True)

    if kind and kind in EditorialEntry.Kind.values:
        stories = stories.filter(kind=kind)

    return render(request, 'community/stories_list.html', {
        'stories': stories,
        'kinds': EditorialEntry.Kind.choices,
        'selected_kind': kind or 'ALL',
    })


@require_GET
def story_detail_view(request, story_id):
    """Detailed view for a single story with typography and related attractions."""
    story = get_object_or_404(EditorialEntry, id=story_id, is_published=True)
    related_stories = EditorialEntry.objects.filter(
        is_published=True
    ).exclude(id=story.id)[:3]

    return render(request, 'community/story_detail.html', {
        'story': story,
        'related_stories': related_stories,
    })


# ---------------------------------------------------------------------------
# Coupon Validation (HTMX Endpoint)
# ---------------------------------------------------------------------------
@require_http_methods(["POST"])
def validate_coupon_htmx_view(request):
    """
    Validates promo code and applies discount dynamically in checkout via HTMX.
    """
    code = request.POST.get("coupon_code", "").strip().upper()
    try:
        order_amount = Decimal(request.POST.get("order_amount", "0"))
    except Exception:
        order_amount = Decimal("0")

    if not code:
        return render(request, "community/partials/coupon_feedback.html", {
            "is_valid": False,
            "message": "กรุณาระบุรหัสคูปองส่วนลด",
            "discount": Decimal("0.00"),
            "final_amount": order_amount,
        })

    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        return render(request, "community/partials/coupon_feedback.html", {
            "is_valid": False,
            "message": f"ไม่พบคูปองรหัส '{code}' ในระบบ",
            "discount": Decimal("0.00"),
            "final_amount": order_amount,
        })

    is_valid, msg = coupon.is_valid_for(order_amount)
    discount = coupon.discount_amount if is_valid else Decimal("0.00")
    final_amount = max(Decimal("0.00"), order_amount - discount)

    return render(request, "community/partials/coupon_feedback.html", {
        "is_valid": is_valid,
        "message": msg,
        "coupon": coupon,
        "discount": discount,
        "final_amount": final_amount,
    })


# ---------------------------------------------------------------------------
# Location Privacy & Consent Management (PDPA Compliant)
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET", "DELETE"])
def my_location_events_view(request):
    """
    PDPA User Rights:
    GET: View the latest coarse location logged in database (HTML or JSON).
    DELETE: Purge all historical location records for this user immediately.
    """
    if request.method == "DELETE":
        deleted_count, _ = LocationEvent.objects.filter(user=request.user).delete()
        record_audit_log(
            request=request,
            action="DELETE",
            model_name="LocationEvent",
            object_id="USER_PURGE",
            changes={"deleted_count": deleted_count},
            user=request.user,
        )
        return JsonResponse({"deleted": True, "count": deleted_count})

    latest_event = LocationEvent.objects.filter(user=request.user).order_by("-created_at").first()

    # If JSON is explicitly requested (e.g. from fetch)
    accept_header = request.headers.get("Accept", "")
    if "application/json" in accept_header and "text/html" not in accept_header:
        if not latest_event:
            return JsonResponse({"has_location": False})
        return JsonResponse({
            "has_location": True,
            "latitude": float(latest_event.latitude) if latest_event.latitude else None,
            "longitude": float(latest_event.longitude) if latest_event.longitude else None,
            "outcome": latest_event.outcome,
            "created_at": latest_event.created_at.strftime("%Y-%m-%d %H:%M น."),
        })

    # Browser navigation: Render full PDPA Privacy Settings HTML page
    return render(request, "community/privacy_settings.html", {
        "latest_event": latest_event,
        "page_title": "ตั้งค่าความเป็นส่วนตัวและพิกัดตำแหน่ง (PDPA) — WellTrip",
    })


@require_http_methods(["POST"])
def record_location_consent_api_view(request):
    """
    Records coarse GPS location consent from tourist (PDPA Data Minimization ~1.1km).
    Logs an AuditLog entry when user is authenticated.
    """
    import json
    from datetime import timedelta
    from django.utils import timezone
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    outcome = data.get("outcome", "denied").lower()
    lat = data.get("latitude")
    lng = data.get("longitude")

    if request.user.is_authenticated:
        coarse_lat = round(Decimal(str(lat)), 2) if lat is not None else None
        coarse_lng = round(Decimal(str(lng)), 2) if lng is not None else None

        event = LocationEvent.objects.create(
            user=request.user,
            outcome=outcome,
            latitude=coarse_lat,
            longitude=coarse_lng,
            expires_at=timezone.now() + timedelta(days=90),
        )

        record_audit_log(
            request=request,
            action="LOCATION_CONSENT",
            model_name="LocationEvent",
            object_id=str(event.id),
            changes={"outcome": outcome, "coarse_lat": str(coarse_lat), "coarse_lng": str(coarse_lng)},
            user=request.user,
        )

    return JsonResponse({"status": "ok", "outcome": outcome})
