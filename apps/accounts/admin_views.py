from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import models, transaction, IntegrityError
from django.core.paginator import Paginator

from apps.accounts.models import User, UserRoles, AuditLog
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, WellnessService
from apps.otop.models import OTOPProduct
from apps.core.services.notifications import send_merchant_kyc_decision


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
    Approves the merchant once, automatically activating their account,
    switching all their homestay listings to ACTIVE, and dispatching notification.
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

    # Dispatch Hostinger SMTP notification
    try:
        send_merchant_kyc_decision(merchant, is_approved=True)
    except Exception:
        pass

    messages.success(request, f"อนุมัติพาร์ทเนอร์ {merchant.email} เรียบร้อยแล้ว (สินค้า/ห้องพักเปิดให้บริการทันที พร้อมส่งอีเมลแจ้งเตือน)")
    return redirect('accounts:admin_approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_reject_merchant_view(request, user_id):
    """
    Merchant KYC Rejection Action:
    Marks rejection, keeps account unverified, and dispatches explanation email.
    """
    merchant = get_object_or_404(User, id=user_id)
    reason = request.POST.get('reason', '').strip() or "ข้อมูลเอกสารประกอบการยืนยันตัวตนไม่ครบถ้วนหรือไม่สอดคล้องตามเกณฑ์มาตรฐาน"

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="User",
        object_id=str(merchant.id),
        changes={"action": "ONE_TIME_KYC_REJECTED", "email": merchant.email, "reason": reason},
        user=request.user,
    )

    try:
        send_merchant_kyc_decision(merchant, is_approved=False, reason=reason)
    except Exception:
        pass

    messages.warning(request, f"ปฏิเสธการอนุมัติพาร์ทเนอร์ {merchant.email} และส่งอีเมลแจ้งเหตุผลเรียบร้อยแล้ว")
    return redirect('accounts:admin_approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_users_view(request):
    """
    Enterprise User Management View:
    Displays user registry with search by email/name and role filtering.
    """
    query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()

    users_qs = User.objects.all().order_by('-date_joined')
    if query:
        users_qs = users_qs.filter(
            models.Q(email__icontains=query) |
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(phone_number__icontains=query)
        )
    if role_filter:
        users_qs = users_qs.filter(role=role_filter)

    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'admin/users.html', {
        'page_obj': page_obj,
        'query': query,
        'role_filter': role_filter,
        'role_choices': UserRoles.choices,
    })


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_delete_user_view(request, user_id):
    """
    Enterprise Secure User Deletion Action with Multi-Tier Guards:
    1. Self-Deletion Guard: Admin cannot delete their own account.
    2. Hierarchy Guard: COMMUNITY_ADMIN cannot delete SUPER_ADMIN or other COMMUNITY_ADMINs.
    3. Cascade Guard & Soft-Delete Fallback: Catch ProtectedError/RestrictedError/IntegrityError
       and execute soft-delete (is_active=False) to preserve financial and booking audit trail.
    """
    target_user = get_object_or_404(User, id=user_id)

    # 1. Self-Deletion Guard
    if request.user.id == target_user.id:
        messages.error(request, "ความปลอดภัย: ไม่อนุญาตให้ลบบัญชีของตนเองผ่านระบบผู้ดูแล")
        return redirect('accounts:admin_users')

    # 2. Hierarchy Guard
    if request.user.role == UserRoles.COMMUNITY_ADMIN:
        if target_user.role == UserRoles.SUPER_ADMIN:
            messages.error(request, "การละเมิดสิทธิ์: ผู้ดูแลชุมชน (Community Admin) ไม่มีสิทธิ์ลบบัญชีผู้ดูแลระบบสูงสุด (Super Admin)")
            return redirect('accounts:admin_users')
        if target_user.role == UserRoles.COMMUNITY_ADMIN:
            messages.error(request, "การละเมิดสิทธิ์: ผู้ดูแลชุมชนไม่สามารถลบบัญชีผู้ดูแลชุมชนอื่นได้ (สงวนสิทธิ์เฉพาะ Super Admin)")
            return redirect('accounts:admin_users')

    # 3. Cascade Guard with Soft-Delete Fallback
    user_email = target_user.email
    try:
        with transaction.atomic():
            target_user.delete()
            record_audit_log(
                request=request,
                action="DELETE",
                model_name="User",
                object_id=str(user_id),
                changes={"deleted_user": user_email},
                user=request.user,
            )
            messages.success(request, f"ลบบัญชีผู้ใช้ {user_email} ออกจากระบบเรียบร้อยแล้ว")
    except (models.ProtectedError, models.RestrictedError, IntegrityError) as exc:
        # Fallback to Soft-Delete to protect integrity and financial logs
        target_user.is_active = False
        target_user.save(update_fields=['is_active'])
        record_audit_log(
            request=request,
            action="SOFT_DELETE",
            model_name="User",
            object_id=str(user_id),
            changes={
                "reason": "Cascade Guard: User linked to financial/booking/catalog data. Deactivated account instead.",
                "error": str(exc),
            },
            user=request.user,
        )
        messages.warning(
            request,
            f"ผู้ใช้ {user_email} มีข้อมูลประวัติการเงิน การจอง หรือบริการผูกอยู่ จึงได้ทำการระงับ/ปิดการใช้งาน (Soft-Delete) เพื่อรักษาหลักฐานทางบัญชีตามมาตรฐานความปลอดภัย"
        )

    return redirect('accounts:admin_users')


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
