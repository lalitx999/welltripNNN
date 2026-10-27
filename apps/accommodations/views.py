from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required, can_edit_object
from apps.accounts.services.audit import record_audit_log
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar, AccommodationStatus
from apps.accommodations.forms import AccommodationForm, RoomForm, RoomPricingCalendarForm


def list_view(request):
    """
    Public list of active homestays for tourists:
    Supports searching by keyword (name/address), filtering by district and price.
    """
    query = request.GET.get('q', '').strip()
    district = request.GET.get('district', '').strip()
    price_range = request.GET.get('priceRange', '').strip()

    qs = Accommodation.objects.filter(status=AccommodationStatus.ACTIVE).select_related('owner').prefetch_related('rooms')

    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(address__icontains=query) |
            Q(subdistrict__icontains=query) |
            Q(district__icontains=query)
        )

    if district:
        qs = qs.filter(district__icontains=district)

    if price_range == 'budget':
        qs = qs.filter(min_price_per_night__lt=800)
    elif price_range == 'mid':
        qs = qs.filter(min_price_per_night__gte=800, min_price_per_night__lte=1500)
    elif price_range == 'luxury':
        qs = qs.filter(min_price_per_night__gt=1500)

    # Districts for filter dropdown
    districts = [
        "เมืองศรีสะเกษ", "กันทรลักษ์", "กันทรารมย์", "ขุนหาญ", "ราษีไศล",
        "อุทุมพรพิสัย", "ปรางค์กู่", "ขุขันธ์", "ไพรบึง", "ห้วยทับทัน",
        "โนนคูณ", "ศรีรัตนะ", "น้ำเกลี้ยง", "วังหิน", "ภูสิงห์", "เมืองจันทร์",
        "เบญจลักษ์", "พยุห์", "โพธิ์ศรีสุวรรณ", "ศิลาลาด"
    ]

    return render(request, 'accommodations/list.html', {
        'accommodations': qs,
        'query': query,
        'selected_district': district,
        'selected_price': price_range,
        'districts': districts,
        'total_count': qs.count(),
    })


def detail_view(request, identifier):
    """
    Public detail view of a single homestay:
    Accepts either UUID or slug, displays rooms, amenities, photo gallery,
    and direct room booking form.
    """
    try:
        accommodation = Accommodation.objects.prefetch_related('rooms').get(slug=identifier, status=AccommodationStatus.ACTIVE)
    except (Accommodation.DoesNotExist, ValueError):
        accommodation = get_object_or_404(Accommodation.objects.prefetch_related('rooms'), id=identifier, status=AccommodationStatus.ACTIVE)

    rooms = accommodation.rooms.filter(is_active=True)

    return render(request, 'accommodations/detail.html', {
        'accommodation': accommodation,
        'rooms': rooms,
    })



@role_required(UserRoles.HOMESTAY_OWNER)
@require_http_methods(["GET", "POST"])
def homestay_studio_view(request):
    """
    Homestay Owner Partner Studio:
    Manages the homestay profile and rooms with strict row-level isolation.
    """
    # Strictly query accommodation owned by request.user (Anti-IDOR)
    accommodation, created = Accommodation.objects.get_or_create(
        owner=request.user,
        defaults={'name': f"โฮมสเตย์ของ {request.user.first_name or request.user.email}"}
    )

    if request.method == "POST":
        form = AccommodationForm(request.POST, instance=accommodation)
        if form.is_valid():
            acc = form.save()
            record_audit_log(
                request=request,
                action="UPDATE",
                model_name="Accommodation",
                object_id=str(acc.id),
                changes=form.cleaned_data,
            )
            messages.success(request, "บันทึกข้อมูลโฮมสเตย์เรียบร้อยแล้ว")
            return redirect('accommodations:homestay_studio')
    else:
        form = AccommodationForm(instance=accommodation)

    rooms = accommodation.rooms.all()
    room_form = RoomForm()

    return render(request, 'portal/homestay.html', {
        'accommodation': accommodation,
        'form': form,
        'rooms': rooms,
        'room_form': room_form,
    })


@role_required(UserRoles.HOMESTAY_OWNER)
@require_http_methods(["POST"])
def room_create_view(request):
    """Adds a new room to the owner's homestay."""
    accommodation = get_object_or_404(Accommodation, owner=request.user)
    form = RoomForm(request.POST)

    if form.is_valid():
        room = form.save(commit=False)
        room.accommodation = accommodation
        room.save()

        record_audit_log(
            request=request,
            action="CREATE",
            model_name="Room",
            object_id=str(room.id),
            changes=form.cleaned_data,
        )
        messages.success(request, f"เพิ่มห้องพัก '{room.name}' เรียบร้อยแล้ว")
    else:
        messages.error(request, "ข้อมูลห้องพักไม่ถูกต้อง กรุณาตรวจสอบ")

    return redirect('accommodations:homestay_studio')


@role_required(UserRoles.HOMESTAY_OWNER)
@require_http_methods(["GET", "POST"])
def calendar_view(request):
    """
    Mini-PMS Room Pricing & Availability Calendar:
    Allows owners to adjust nightly prices and availability.
    """
    accommodation = get_object_or_404(Accommodation, owner=request.user)
    rooms = accommodation.rooms.all()

    selected_room_id = request.GET.get('room_id') or (rooms.first().id if rooms.exists() else None)
    selected_room = get_object_or_404(Room, id=selected_room_id, accommodation=accommodation) if selected_room_id else None

    if request.method == "POST" and selected_room:
        form = RoomPricingCalendarForm(request.POST)
        if form.is_valid():
            pricing, created = RoomPricingCalendar.objects.update_or_create(
                room=selected_room,
                date=form.cleaned_data['date'],
                defaults={
                    'price': form.cleaned_data['price'],
                    'available_count': form.cleaned_data['available_count'],
                }
            )
            record_audit_log(
                request=request,
                action="UPDATE" if not created else "CREATE",
                model_name="RoomPricingCalendar",
                object_id=str(pricing.id),
                changes={
                    'date': str(pricing.date),
                    'price': str(pricing.price),
                    'available_count': pricing.available_count
                },
            )
            messages.success(request, f"อัปเดตราคาและจำนวนห้องว่างวันที่ {pricing.date} สำเร็จ")
            return redirect(f"{request.path}?room_id={selected_room.id}")

    pricing_list = selected_room.pricing_calendars.order_by('date')[:30] if selected_room else []
    form = RoomPricingCalendarForm()

    return render(request, 'portal/calendar.html', {
        'accommodation': accommodation,
        'rooms': rooms,
        'selected_room': selected_room,
        'pricing_list': pricing_list,
        'form': form,
    })
