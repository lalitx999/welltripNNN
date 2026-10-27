from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot
from apps.services.forms import FoodMenuForm, WellnessServiceForm, WellnessTimeSlotForm


from django.db.models import Q


def list_view(request):
    """
    Public list of healthy dining menus and wellness spa services:
    Supports filtering by active category tab ('all', 'FOOD', 'SPA') and search query.
    """
    category = request.GET.get('category', 'all').strip()
    query = request.GET.get('q', '').strip()

    menus_qs = FoodMenu.objects.filter(is_available=True).select_related('owner')
    services_qs = WellnessService.objects.filter(is_active=True).select_related('owner')

    if query:
        menus_qs = menus_qs.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(ingredients__icontains=query)
        )
        services_qs = services_qs.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(benefits__icontains=query)
        )

    return render(request, 'services/list.html', {
        'menus': menus_qs,
        'food_menus': menus_qs,
        'services': services_qs,
        'wellness_services': services_qs,
        'active_category': category,
        'query': query,
        'total_menus': menus_qs.count(),
        'total_services': services_qs.count(),
    })


def service_detail_view(request, service_type, item_id):
    """Detail view for a single food menu or wellness service."""
    if service_type == 'food':
        item = get_object_or_404(FoodMenu.objects.select_related('owner'), id=item_id, is_available=True)
        return render(request, 'services/detail.html', {
            'item': item,
            'service_type': 'food',
        })
    elif service_type in ('wellness', 'spa'):
        item = get_object_or_404(WellnessService.objects.select_related('owner'), id=item_id, is_active=True)
        slots = item.time_slots.filter(capacity_available__gt=0).order_by('slot_date', 'start_time')
        return render(request, 'services/detail.html', {
            'item': item,
            'service_type': 'wellness',
            'slots': slots,
        })
    else:
        return redirect('services:list')



# ==============================================================================
# RESTAURANT PARTNER STUDIO
# ==============================================================================

@role_required(UserRoles.RESTAURANT_OWNER)
@require_http_methods(["GET", "POST"])
def restaurant_studio_view(request):
    """Manages healthy food menus with 5 ecological wellness categories."""
    if request.method == "POST":
        form = FoodMenuForm(request.POST, request.FILES)
        if form.is_valid():
            menu = form.save(commit=False)
            menu.owner = request.user
            menu.save()

            record_audit_log(
                request=request,
                action="CREATE",
                model_name="FoodMenu",
                object_id=str(menu.id),
                changes=form.cleaned_data,
            )
            messages.success(request, f"เพิ่มเมนู '{menu.name}' สำเร็จ")
            return redirect('services:restaurant_studio')
        else:
            messages.error(request, "ข้อมูลเมนูไม่ถูกต้อง กรุณาตรวจสอบ")
    else:
        form = FoodMenuForm()

    menus = FoodMenu.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'portal/restaurant.html', {
        'menus': menus,
        'form': form,
    })


@role_required(UserRoles.RESTAURANT_OWNER)
@require_http_methods(["POST"])
def food_delete_view(request, food_id):
    """Deletes a menu item, strictly scoped to owner=request.user (Anti-IDOR)."""
    menu = get_object_or_404(FoodMenu, id=food_id, owner=request.user)
    name = menu.name
    menu.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="FoodMenu",
        object_id=str(food_id),
        changes={"name": name},
    )
    messages.success(request, f"ลบเมนู '{name}' เรียบร้อยแล้ว")
    return redirect('services:restaurant_studio')


# ==============================================================================
# WELLNESS & SPA STUDIO
# ==============================================================================

@role_required(UserRoles.WELLNESS_OWNER)
@require_http_methods(["GET", "POST"])
def wellness_studio_view(request):
    """Manages massage/spa treatments and scheduling time slots."""
    if request.method == "POST":
        form = WellnessServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.owner = request.user
            service.save()

            record_audit_log(
                request=request,
                action="CREATE",
                model_name="WellnessService",
                object_id=str(service.id),
                changes=form.cleaned_data,
            )
            messages.success(request, f"เพิ่มบริการ '{service.name}' สำเร็จ")
            return redirect('services:wellness_studio')
    else:
        form = WellnessServiceForm()

    services = WellnessService.objects.filter(owner=request.user).order_by('-created_at')
    
    # Get all upcoming slots for the owner's services
    slots = WellnessTimeSlot.objects.filter(service__owner=request.user).select_related('service').order_by('date', 'start_time')[:30]
    slot_form = WellnessTimeSlotForm()

    return render(request, 'portal/wellness.html', {
        'services': services,
        'slots': slots,
        'form': form,
        'slot_form': slot_form,
    })


@role_required(UserRoles.WELLNESS_OWNER)
@require_http_methods(["POST"])
def wellness_slot_create_view(request):
    """Creates a new time slot for a specified wellness service."""
    service_id = request.POST.get('service_id')
    service = get_object_or_404(WellnessService, id=service_id, owner=request.user)

    form = WellnessTimeSlotForm(request.POST)
    if form.is_valid():
        slot = form.save(commit=False)
        slot.service = service
        slot.capacity_available = slot.capacity_total
        slot.save()

        record_audit_log(
            request=request,
            action="CREATE",
            model_name="WellnessTimeSlot",
            object_id=str(slot.id),
            changes=form.cleaned_data,
        )
        messages.success(request, f"เพิ่มรอบเวลา {slot.start_time.strftime('%H:%M')} สำเร็จ")
    else:
        messages.error(request, "ข้อมูลรอบเวลาไม่ถูกต้อง")

    return redirect('services:wellness_studio')


@role_required(UserRoles.WELLNESS_OWNER)
@require_http_methods(["POST"])
def wellness_slot_delete_view(request, slot_id):
    """Deletes a time slot, strictly verifying ownership."""
    slot = get_object_or_404(WellnessTimeSlot, id=slot_id, service__owner=request.user)
    slot.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="WellnessTimeSlot",
        object_id=str(slot_id),
    )
    messages.success(request, "ลบรอบบริการเรียบร้อยแล้ว")
    return redirect('services:wellness_studio')
