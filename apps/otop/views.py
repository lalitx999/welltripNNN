from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.db import transaction
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRoles
from apps.accounts.permissions import is_platform_admin, role_required, scope_to_owner
from apps.accounts.services.audit import record_audit_log
from apps.otop.models import OTOPProduct
from apps.otop.forms import OTOPProductForm, StockAdjustmentForm


from django.db.models import Q
from apps.otop.models import OTOPProduct, OTOPCategory
from django.utils.translation import gettext as _


def list_view(request):
    """
    Public list of community OTOP retail products:
    Supports filtering by category, search by query 'q', and stock status.
    """
    category = request.GET.get('category', '').strip()
    query = request.GET.get('q', '').strip()

    qs = OTOPProduct.objects.filter(is_active=True).select_related('owner__merchant_profile')

    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    if category:
        qs = qs.filter(category=category)

    return render(request, 'otop/list.html', {
        'products': qs,
        'categories': OTOPCategory.choices,
        'selected_category': category,
        'query': query,
        'total_count': qs.count(),
    })


def detail_view(request, product_id):
    """Public detail view for a single OTOP retail product."""
    product = get_object_or_404(OTOPProduct.objects.select_related('owner__merchant_profile'), id=product_id, is_active=True)
    return render(request, 'otop/detail.html', {
        'product': product,
    })



@role_required(UserRoles.OTOP_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def otop_studio_view(request):
    """
    OTOP Partner Studio:
    Manages community products with direct inline stock quantity adjustment.
    """
    can_create = not is_platform_admin(request.user)
    if request.method == "POST" and not can_create:
        messages.error(request, _("ผู้ดูแลระบบแก้ไขหรือปิดสินค้าได้ แต่การเพิ่มสินค้าต้องทำจากบัญชีร้านค้า"))
        return redirect('otop:otop_studio')
    if request.method == "POST":
        form = OTOPProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.owner = request.user
            product.save()

            record_audit_log(
                request=request,
                action="CREATE",
                model_name="OTOPProduct",
                object_id=str(product.id),
                changes=form.cleaned_data,
            )
            messages.success(request, _("เพิ่มสินค้า OTOP '{name}' สำเร็จ").format(name=product.name))
            return redirect('otop:otop_studio')
        else:
            messages.error(request, _("ข้อมูลสินค้าไม่ถูกต้อง กรุณาตรวจสอบ"))
    else:
        form = OTOPProductForm()

    products = scope_to_owner(OTOPProduct.objects.select_related('owner__merchant_profile'), request.user).order_by('-created_at')
    return render(request, 'portal/otop.html', {
        'products': products,
        'form': form,
        'can_create': can_create,
    })


@role_required(UserRoles.OTOP_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def otop_stock_update_view(request, product_id):
    """
    HTMX Inline Stock Adjustment Endpoint:
    Adjusts stock_quantity directly without full page reload.
    Guarantees stock cannot become negative (Anti-Negative Stock).
    """
    form = StockAdjustmentForm(request.POST)

    if form.is_valid():
        delta = form.cleaned_data['delta']
        # Lock the row: checkout decrements the same column at the same time
        with transaction.atomic():
            product = get_object_or_404(
                scope_to_owner(OTOPProduct.objects.select_for_update(), request.user), id=product_id
            )
            new_quantity = product.stock_quantity + delta
            if new_quantity < 0:
                return HttpResponse(
                    _("<span class=\"text-xs text-rose-600 font-semibold\">สต็อกไม่สามารถต่ำกว่า 0 ได้</span>").format(),
                    status=400
                )
            old_quantity = product.stock_quantity
            product.stock_quantity = new_quantity
            product.save(update_fields=['stock_quantity', 'updated_at'])

        record_audit_log(
            request=request,
            action="UPDATE",
            model_name="OTOPProduct",
            object_id=str(product.id),
            changes={'stock_quantity': {'from': old_quantity, 'to': new_quantity}},
        )

        return render(request, 'portal/partials/otop_stock_counter.html', {
            'product': product,
        })

    return HttpResponseBadRequest("Invalid adjustment delta")


@role_required(UserRoles.OTOP_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["GET", "POST"])
def product_edit_view(request, product_id):
    """Edit a product's details. Stock stays on the +/- counter so it is always locked."""
    product = get_object_or_404(scope_to_owner(OTOPProduct.objects.all(), request.user), id=product_id)
    form = OTOPProductForm(request.POST or None, request.FILES or None, instance=product)
    form.fields.pop('stock_quantity', None)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit_log(
            request=request, action="UPDATE", model_name="OTOPProduct", object_id=str(product.id),
            changes={k: str(v) for k, v in form.cleaned_data.items() if k != 'image'},
        )
        messages.success(request, _("บันทึก '{name}' เรียบร้อยแล้ว").format(name=product.name))
        return redirect('otop:otop_studio')
    return render(request, 'portal/item_edit.html', {
        'form': form, 'item': product, 'item_label': _("สินค้า OTOP"), 'back_url': reverse('otop:otop_studio'),
    })


@role_required(UserRoles.OTOP_OWNER, UserRoles.COMMUNITY_ADMIN)
@require_http_methods(["POST"])
def product_toggle_view(request, product_id):
    """Open or close a product for sale; closing keeps past orders intact."""
    product = get_object_or_404(scope_to_owner(OTOPProduct.objects.all(), request.user), id=product_id)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active', 'updated_at'])
    record_audit_log(
        request=request, action="UPDATE", model_name="OTOPProduct", object_id=str(product.id),
        changes={'is_active': product.is_active},
    )
    if product.is_active:
        messages.success(request, _("เปิดขาย '{name}' แล้ว").format(name=product.name))
    else:
        messages.success(request, _("ปิดการขาย '{name}' แล้ว ลูกค้าจะไม่เห็นสินค้านี้").format(name=product.name))
    return redirect('otop:otop_studio')
