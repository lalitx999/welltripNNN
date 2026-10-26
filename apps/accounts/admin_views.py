from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction

from apps.accounts.models import User, UserRoles, AuditLog
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, WellnessService
from apps.otop.models import OTOPProduct


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_approvals_view(request):
    """
    One-Time Merchant KYC Approval View:
    Displays pending partner registrations and unapproved homestays.
    """
    # Pending Merchants (email_verified=False or unapproved)
    pending_merchants = User.objects.filter(
        role__in=[
            UserRoles.HOMESTAY_OWNER,
            UserRoles.RESTAURANT_OWNER,
            UserRoles.WELLNESS_OWNER,
            UserRoles.OTOP_OWNER,
        ],
        email_verified=False,
    ).order_by('-date_joined')

    # Pending Homestays
    pending_accommodations = Accommodation.objects.filter(
        status=AccommodationStatus.PENDING_VERIFICATION
    ).select_related('owner').order_by('-created_at')

    return render(request, 'admin/approvals.html', {
        'pending_merchants': pending_merchants,
        'pending_accommodations': pending_accommodations,
    })


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_approve_merchant_view(request, user_id):
    """
    One-Time Merchant Approval Action:
    Approves the merchant once, automatically activating their account
    and switching all their homestay listings to ACTIVE.
    """
    merchant = get_object_or_404(User, id=user_id)

    with transaction.atomic():
        merchant.email_verified = True
        merchant.is_active = True
        merchant.save(update_fields=['email_verified', 'is_active'])

        # Auto-activate any accommodations owned by this merchant
        Accommodation.objects.filter(owner=merchant).update(status=AccommodationStatus.ACTIVE)

        record_audit_log(
            request=request,
            action="UPDATE",
            model_name="User",
            object_id=str(merchant.id),
            changes={"action": "ONE_TIME_KYC_APPROVED", "email": merchant.email, "role": merchant.role},
            user=request.user,
        )

    messages.success(request, f"อนุมัติพาร์ทเนอร์ {merchant.email} เรียบร้อยแล้ว (สินค้า/ห้องพักเปิดให้บริการทันที)")
    return redirect('accounts:admin_approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_catalog_view(request):
    """
    Unified Catalog Audit View:
    Displays all accommodations, food menus, wellness services, and OTOP products
    with real owner contact details (Name, Email, Phone).
    """
    accommodations = Accommodation.objects.select_related('owner').order_by('-created_at')[:20]
    menus = FoodMenu.objects.select_related('owner').order_by('-created_at')[:20]
    spas = WellnessService.objects.select_related('owner').order_by('-created_at')[:20]
    otop_items = OTOPProduct.objects.select_related('owner').order_by('-created_at')[:20]

    return render(request, 'admin/catalog.html', {
        'accommodations': accommodations,
        'menus': menus,
        'spas': spas,
        'otop_items': otop_items,
    })


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_audit_log_view(request):
    """
    Security Audit Log Viewer:
    Displays historical audit events with 90-day retention inspection.
    """
    action_filter = request.GET.get('action')
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')

    if action_filter:
        logs = logs.filter(action=action_filter)

    return render(request, 'admin/audit_logs.html', {
        'logs': logs[:100],
        'action_filter': action_filter,
    })
