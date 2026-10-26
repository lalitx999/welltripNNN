from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET

from apps.accounts.services.audit import record_audit_log
from apps.community.models import MapLocation, PassportStamp, MapLocationCategory


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
    """Digital Passport book showing tourist's collected stamps and badges."""
    stamps = PassportStamp.objects.filter(user=request.user).select_related('location').order_by('-stamped_at')
    stamp_count = stamps.count()

    # Determine Explorer Level
    if stamp_count >= 10:
        badge = {"name": "Gold Community Ambassador", "color": "bg-gold text-forest", "icon": "👑"}
    elif stamp_count >= 5:
        badge = {"name": "Silver Cultural Explorer", "color": "bg-slate-200 text-slate-800", "icon": "🥈"}
    elif stamp_count >= 1:
        badge = {"name": "Bronze Heritage Scout", "color": "bg-amber-100 text-amber-900", "icon": "🥉"}
    else:
        badge = {"name": "Novice Traveler", "color": "bg-gray-100 text-gray-600", "icon": "🧭"}

    all_locations = MapLocation.objects.filter(is_active=True).count()

    return render(request, 'community/passport.html', {
        'stamps': stamps,
        'stamp_count': stamp_count,
        'all_locations': all_locations,
        'badge': badge,
    })


@login_required
def claim_stamp_view(request, qr_secret):
    """
    Endpoint reached when tourist scans physical QR code at a venue.
    Validates QR secret and awards digital stamp.
    """
    location = get_object_or_404(MapLocation, qr_secret=qr_secret, is_active=True)

    stamp, created = PassportStamp.objects.get_or_create(
        user=request.user,
        location=location,
    )

    if created:
        record_audit_log(
            request=request,
            action="CREATE",
            model_name="PassportStamp",
            object_id=str(stamp.id),
            changes={"location_title": location.title, "category": location.category},
            user=request.user,
        )
        messages.success(request, f"🎉 ยินดีด้วย! คุณได้รับตราประทับ '{location.title}' เรียบร้อยแล้ว")
    else:
        messages.info(request, f"คุณเคยได้รับตราประทับของ '{location.title}' ไปแล้ว")

    return redirect('community:passport')
