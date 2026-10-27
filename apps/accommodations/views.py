from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone

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
    price_range = (request.GET.get('price') or request.GET.get('priceRange') or '').strip()

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

    if price_range in ('budget', 'economy'):
        qs = qs.filter(min_price_per_night__lt=800)
    elif price_range in ('mid', 'moderate'):
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
        accommodation = Accommodation.objects.select_related('owner').prefetch_related('rooms__images').get(slug=identifier, status=AccommodationStatus.ACTIVE)
    except (Accommodation.DoesNotExist, ValueError):
        accommodation = get_object_or_404(Accommodation.objects.select_related('owner').prefetch_related('rooms__images'), id=identifier, status=AccommodationStatus.ACTIVE)

    rooms = accommodation.rooms.filter(is_active=True).prefetch_related('images')

    return render(request, 'accommodations/detail.html', {
        'accommodation': accommodation,
        'rooms': rooms,
    })



@role_required(UserRoles.HOMESTAY_OWNER, UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def homestay_studio_view(request):
    """
    Homestay Owner Partner Studio:
    Manages the homestay profile and rooms with strict row-level isolation.
    """
    if request.user.is_superuser or request.user.role == UserRoles.COMMUNITY_ADMIN:
        owner_accommodations = Accommodation.objects.all()
    else:
        owner_accommodations = Accommodation.objects.filter(owner=request.user)

    acc_id = request.GET.get('acc_id') or request.POST.get('accommodation_id')
    if acc_id:
        accommodation = owner_accommodations.filter(id=acc_id).first()
    else:
        accommodation = owner_accommodations.first()

    if not accommodation:
        accommodation = Accommodation.objects.create(
            owner=request.user,
            name=f"โฮมสเตย์ของ {request.user.first_name or request.user.email}",
            status=AccommodationStatus.ACTIVE,
        )
        owner_accommodations = Accommodation.objects.filter(owner=request.user)

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
            messages.success(request, f"บันทึกข้อมูล '{acc.name}' เรียบร้อยแล้ว")
            return redirect(f"{request.path}?acc_id={acc.id}")
    else:
        form = AccommodationForm(instance=accommodation)

    rooms = accommodation.rooms.all()
    room_form = RoomForm()

    return render(request, 'portal/homestay.html', {
        'accommodation': accommodation,
        'owner_accommodations': owner_accommodations,
        'form': form,
        'rooms': rooms,
        'room_form': room_form,
    })


@role_required(UserRoles.HOMESTAY_OWNER, UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def room_create_view(request):
    """Adds a new room to the owner's homestay."""
    acc_id = request.POST.get('accommodation_id')
    if request.user.is_superuser or request.user.role == UserRoles.COMMUNITY_ADMIN:
        accommodation = get_object_or_404(Accommodation, id=acc_id) if acc_id else Accommodation.objects.first()
    else:
        accommodation = get_object_or_404(Accommodation, id=acc_id, owner=request.user) if acc_id else Accommodation.objects.filter(owner=request.user).first()

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

    return redirect(f"/accommodations/studio/?acc_id={accommodation.id}")


@role_required(UserRoles.HOMESTAY_OWNER, UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def room_delete_view(request, room_id):
    """Deletes a room from the owner's homestay."""
    if request.user.is_superuser or request.user.role == UserRoles.COMMUNITY_ADMIN:
        room = get_object_or_404(Room, id=room_id)
    else:
        room = get_object_or_404(Room, id=room_id, accommodation__owner=request.user)

    acc_id = room.accommodation_id
    room_name = room.name
    room.delete()
    messages.success(request, f"ลบห้องพัก '{room_name}' เรียบร้อยแล้ว")
    return redirect(f"/accommodations/studio/?acc_id={acc_id}")


@role_required(UserRoles.HOMESTAY_OWNER, UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def calendar_view(request):
    """
    Mini-PMS Room Pricing & Availability Calendar:
    Allows owners to adjust nightly prices and availability.
    """
    if request.user.is_superuser or request.user.role == UserRoles.COMMUNITY_ADMIN:
        owner_accommodations = Accommodation.objects.all()
    else:
        owner_accommodations = Accommodation.objects.filter(owner=request.user)

    acc_id = request.GET.get('acc_id')
    if acc_id:
        accommodation = owner_accommodations.filter(id=acc_id).first()
    else:
        accommodation = owner_accommodations.first()

    if not accommodation:
        messages.warning(request, "ยังไม่มีข้อมูลที่พัก กรุณาสร้างที่พักก่อนจัดการปฏิทิน")
        return redirect('accommodations:homestay_studio')

    rooms = accommodation.rooms.all()
    selected_room_id = request.GET.get('room_id') or (rooms.first().id if rooms.exists() else None)
    selected_room = rooms.filter(id=selected_room_id).first() if selected_room_id else None

    import calendar
    from datetime import date

    # Year & Month determination
    try:
        year = int(request.GET.get('year') or timezone.now().year)
        month = int(request.GET.get('month') or timezone.now().month)
        if not (1 <= month <= 12):
            month = timezone.now().month
    except (ValueError, TypeError):
        year = timezone.now().year
        month = timezone.now().month

    # Prev and Next month navigation
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year

    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year

    thai_months = [
        "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    month_name = f"{thai_months[month]} {year + 543}"

    if request.method == "POST" and selected_room:
        form = RoomPricingCalendarForm(request.POST)
        if form.is_valid():
            p_date = form.cleaned_data['date']
            pricing, created = RoomPricingCalendar.objects.update_or_create(
                room=selected_room,
                date=p_date,
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
            return redirect(f"{request.path}?acc_id={accommodation.id}&room_id={selected_room.id}&year={p_date.year}&month={p_date.month}")

    # Build Calendar Matrix
    cal = calendar.monthcalendar(year, month)
    pricing_map = {}
    if selected_room:
        for p in RoomPricingCalendar.objects.filter(room=selected_room, date__year=year, date__month=month):
            pricing_map[p.date.day] = p

    calendar_weeks = []
    today = timezone.now().date()
    for week in cal:
        week_days = []
        for day in week:
            if day == 0:
                week_days.append(None)
            else:
                day_date = date(year, month, day)
                p = pricing_map.get(day)
                price = p.price if p else (selected_room.base_price_per_night if selected_room else Decimal("650.00"))
                available_count = p.available_count if p else (selected_room.total_rooms_count if selected_room else 1)
                is_custom = p is not None
                is_past = day_date < today
                is_today = day_date == today
                week_days.append({
                    'day': day,
                    'date_str': day_date.strftime('%Y-%m-%d'),
                    'price': price,
                    'available_count': available_count,
                    'total_count': selected_room.total_rooms_count if selected_room else 1,
                    'is_custom': is_custom,
                    'is_past': is_past,
                    'is_today': is_today,
                    'is_sold_out': available_count <= 0,
                })
        calendar_weeks.append(week_days)

    form = RoomPricingCalendarForm()

    return render(request, 'portal/calendar.html', {
        'accommodation': accommodation,
        'owner_accommodations': owner_accommodations,
        'rooms': rooms,
        'selected_room': selected_room,
        'calendar_weeks': calendar_weeks,
        'year': year,
        'month': month,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'month_name': month_name,
        'form': form,
    })
