from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.otop.models import OTOPProduct
from apps.otop.forms import OTOPProductForm, StockAdjustmentForm


from django.db.models import Q
from apps.otop.models import OTOPProduct, OTOPCategory


def list_view(request):
    """
    Public list of community OTOP retail products:
    Supports filtering by category, search by query 'q', and stock status.
    """
    category = request.GET.get('category', '').strip()
    query = request.GET.get('q', '').strip()

    qs = OTOPProduct.objects.filter(is_active=True).select_related('owner')

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
    product = get_object_or_404(OTOPProduct.objects.select_related('owner'), id=product_id, is_active=True)
    return render(request, 'otop/detail.html', {
        'product': product,
    })



@role_required(UserRoles.OTOP_OWNER)
@require_http_methods(["GET", "POST"])
def otop_studio_view(request):
    """
    OTOP Partner Studio:
    Manages community products with direct inline stock quantity adjustment.
    """
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
            messages.success(request, f"เพิ่มสินค้า OTOP '{product.name}' สำเร็จ")
            return redirect('otop:otop_studio')
        else:
            messages.error(request, "ข้อมูลสินค้าไม่ถูกต้อง กรุณาตรวจสอบ")
    else:
        form = OTOPProductForm()

    products = OTOPProduct.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'portal/otop.html', {
        'products': products,
        'form': form,
    })


@role_required(UserRoles.OTOP_OWNER)
@require_http_methods(["POST"])
def otop_stock_update_view(request, product_id):
    """
    HTMX Inline Stock Adjustment Endpoint:
    Adjusts stock_quantity directly without full page reload.
    Guarantees stock cannot become negative (Anti-Negative Stock).
    """
    product = get_object_or_404(OTOPProduct, id=product_id, owner=request.user)
    form = StockAdjustmentForm(request.POST)

    if form.is_valid():
        delta = form.cleaned_data['delta']
        new_quantity = product.stock_quantity + delta

        if new_quantity < 0:
            return HttpResponse(
                f'<span class="text-xs text-rose-600 font-semibold">สต็อกไม่สามารถต่ำกว่า 0 ได้</span>',
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
