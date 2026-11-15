from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRoles
from apps.accounts.permissions import is_platform_admin, role_required, scope_to_owner
from apps.accounts.services.audit import record_audit_log
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot
from apps.services.forms import FoodMenuForm, WellnessServiceForm, WellnessTimeSlotForm


from django.db.models import Q
from django.utils.translation import gettext as _, gettext_lazy


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
        slots = item.time_slots.filter(capacity_available__gt=0).order_by('date', 'start_time')
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

@role_required(UserRoles.RESTAURANT_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def restaurant_studio_view(request):
    """Manages healthy food menus with 5 ecological wellness categories."""
    can_create = not is_platform_admin(request.user)
    if request.method == "POST" and not can_create:
        messages.error(request, _("ผู้ดูแลระบบแก้ไขหรือปิดเมนูได้ แต่การเพิ่มเมนูต้องทำจากบัญชีร้านค้า"))
        return redirect('services:restaurant_studio')
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
            messages.success(request, _("เพิ่มเมนู '{name}' สำเร็จ").format(name=menu.name))
            return redirect('services:restaurant_studio')
        else:
            messages.error(request, _("ข้อมูลเมนูไม่ถูกต้อง กรุณาตรวจสอบ"))
    else:
        form = FoodMenuForm()

    menus = scope_to_owner(FoodMenu.objects.select_related('owner'), request.user).order_by('-created_at')
    return render(request, 'portal/restaurant.html', {
        'menus': menus,
        'form': form,
        'can_create': can_create,
    })


@role_required(UserRoles.RESTAURANT_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def food_delete_view(request, food_id):
    """Deletes a menu item, strictly scoped to owner=request.user (Anti-IDOR)."""
    menu = get_object_or_404(scope_to_owner(FoodMenu.objects.all(), request.user), id=food_id)
    name = menu.name
    menu.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="FoodMenu",
        object_id=str(food_id),
        changes={"name": name},
    )
    messages.success(request, _("ลบเมนู '{name}' เรียบร้อยแล้ว").format(name=name))
    return redirect('services:restaurant_studio')


# ==============================================================================
# WELLNESS & SPA STUDIO
# ==============================================================================

@role_required(UserRoles.WELLNESS_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def wellness_studio_view(request):
    """Manages massage/spa treatments and scheduling time slots."""
    can_create = not is_platform_admin(request.user)
    if request.method == "POST" and not can_create:
        messages.error(request, _("ผู้ดูแลระบบแก้ไขหรือปิดบริการได้ แต่การเพิ่มบริการต้องทำจากบัญชีร้านค้า"))
        return redirect('services:wellness_studio')
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
            messages.success(request, _("เพิ่มบริการ '{name}' สำเร็จ").format(name=service.name))
            return redirect('services:wellness_studio')
    else:
        form = WellnessServiceForm()

    services = scope_to_owner(WellnessService.objects.select_related('owner'), request.user).order_by('-created_at')

    # Upcoming slots for the services shown
    slots = (
        scope_to_owner(WellnessTimeSlot.objects.select_related('service'), request.user, 'service__owner')
        .filter(date__gte=timezone.localdate())
        .order_by('date', 'start_time')[:30]
    )
    slot_form = WellnessTimeSlotForm()

    return render(request, 'portal/wellness.html', {
        'services': services,
        'slots': slots,
        'form': form,
        'service_form': form,  # the template's add-service card reads this name
        'slot_form': slot_form,
        'can_create': can_create,
    })


@role_required(UserRoles.WELLNESS_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def wellness_slot_create_view(request):
    """Creates a new time slot for a specified wellness service."""
    service_id = request.POST.get('service_id')
    service = get_object_or_404(scope_to_owner(WellnessService.objects.all(), request.user), id=service_id)

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
        messages.success(request, _("เพิ่มรอบเวลา {strftime} สำเร็จ").format(strftime=slot.start_time.strftime('%H:%M')))
    else:
        messages.error(request, _("ข้อมูลรอบเวลาไม่ถูกต้อง"))

    return redirect('services:wellness_studio')


@role_required(UserRoles.WELLNESS_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def wellness_slot_delete_view(request, slot_id):
    """Deletes a time slot, strictly verifying ownership."""
    slot = get_object_or_404(scope_to_owner(WellnessTimeSlot.objects.all(), request.user, 'service__owner'), id=slot_id)
    slot.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="WellnessTimeSlot",
        object_id=str(slot_id),
    )
    messages.success(request, _("ลบรอบบริการเรียบร้อยแล้ว"))
    return redirect('services:wellness_studio')


# ==============================================================================
# EDIT & OPEN/CLOSE (menus and spa services)
# ==============================================================================

_EDITABLE = {
    # kind: (model, form, studio url name, label, availability field)
    'food': (FoodMenu, FoodMenuForm, 'services:restaurant_studio', gettext_lazy("เมนูอาหาร"), 'is_available'),
    'wellness': (WellnessService, WellnessServiceForm, 'services:wellness_studio', gettext_lazy("บริการสปา"), 'is_active'),
}


def _owned_item(request, kind, item_id):
    if kind not in _EDITABLE:
        raise Http404
    model = _EDITABLE[kind][0]
    if not (is_platform_admin(request.user) or request.user.role == (
        UserRoles.RESTAURANT_OWNER if kind == 'food' else UserRoles.WELLNESS_OWNER
    )):
        raise Http404
    return get_object_or_404(scope_to_owner(model.objects.all(), request.user), id=item_id)


@role_required(UserRoles.RESTAURANT_OWNER, UserRoles.WELLNESS_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def service_item_edit_view(request, kind, item_id):
    """Edit a food menu or spa service the partner owns (admins: any)."""
    item = _owned_item(request, kind, item_id)
    _model, form_class, studio, label, _flag = _EDITABLE[kind]
    form = form_class(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit_log(
            request=request, action="UPDATE", model_name=item.__class__.__name__,
            object_id=str(item.id), changes={k: str(v) for k, v in form.cleaned_data.items() if k != 'image'},
        )
        messages.success(request, _("บันทึก '{name}' เรียบร้อยแล้ว").format(name=item.name))
        return redirect(studio)
    return render(request, 'portal/item_edit.html', {
        'form': form, 'item': item, 'item_label': label, 'back_url': reverse(studio),
    })


@role_required(UserRoles.RESTAURANT_OWNER, UserRoles.WELLNESS_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def service_item_toggle_view(request, kind, item_id):
    """Open or close an item for sale; closing keeps it for order history."""
    item = _owned_item(request, kind, item_id)
    _model, _form, studio, _label, flag = _EDITABLE[kind]
    setattr(item, flag, not getattr(item, flag))
    item.save(update_fields=[flag, 'updated_at'])
    record_audit_log(
        request=request, action="UPDATE", model_name=item.__class__.__name__,
        object_id=str(item.id), changes={flag: getattr(item, flag)},
    )
    if getattr(item, flag):
        messages.success(request, _("เปิดขาย '{name}' แล้ว").format(name=item.name))
    else:
        messages.success(request, _("ปิดการขาย '{name}' แล้ว ลูกค้าจะไม่เห็นรายการนี้").format(name=item.name))
    return redirect(studio)
