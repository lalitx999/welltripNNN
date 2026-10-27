from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import models, transaction, IntegrityError
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.utils import timezone

from apps.accounts.models import User, UserRoles, AuditLog, MerchantProfile, MerchantApprovalStatus
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, WellnessService
from apps.otop.models import OTOPProduct
from apps.payments.models import Payment, PaymentStatus, PaymentSlip, SlipVerificationStatus
from apps.bookings.models import Booking, BookingStatus
from apps.community.models import MapLocation, PassportStamp, LocationEvent, EditorialEntry
from apps.core.services.notifications import send_merchant_kyc_decision


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_command_center_view(request):
    """
    Unified Single-Page Command Center (Modern Admin Dashboard)
    Replaces default factory admin with a high-transparency operations console.
    Supports 7 core modules from Documents/welltrip via ?tab=...:
    1. overview - ภาพรวมระบบ & KPIs
    2. payments - ตรวจสอบสลิปโอนเงิน (Slips)
    3. approvals - อนุมัติผู้ประกอบการชุมชน (Merchant KYC)
    4. catalog - จัดการแคตตาล็อก 4 หมวด
    5. users - จัดการผู้ใช้งานและสิทธิ์
    6. locations - จุดเช็คอิน & บันทึกพาสปอร์ต
    7. content - เรื่องราว & บทความมรดกชุมชน
    """
    active_tab = request.GET.get('tab', 'overview').strip().lower()
    now = timezone.now()

    # -------------------------------------------------------------------------
    # 1. Global Operational KPIs
    # -------------------------------------------------------------------------
    total_users_count = User.objects.count()
    tourists_count = User.objects.filter(role=UserRoles.TOURIST).count()
    merchants_count = User.objects.filter(role__in=[
        UserRoles.HOMESTAY_OWNER,
        UserRoles.RESTAURANT_OWNER,
        UserRoles.WELLNESS_OWNER,
        UserRoles.OTOP_OWNER,
    ]).count()

    pending_kyc_count = MerchantProfile.objects.filter(status=MerchantApprovalStatus.PENDING).count()
    # Fallback to unverified legacy merchant accounts if any
    legacy_pending_kyc = User.objects.filter(
        role__in=[
            UserRoles.HOMESTAY_OWNER,
            UserRoles.RESTAURANT_OWNER,
            UserRoles.WELLNESS_OWNER,
            UserRoles.OTOP_OWNER,
        ],
        email_verified=False
    ).exclude(merchant_profile__isnull=False).count()
    total_pending_kyc = pending_kyc_count + legacy_pending_kyc

    pending_slips_count = Payment.objects.filter(status=PaymentStatus.PENDING).count()
    total_bookings_count = Booking.objects.count()
    
    total_revenue = Payment.objects.filter(status=PaymentStatus.SUCCESS).aggregate(
        total=Sum('amount')
    )['total'] or 0

    total_stays = Accommodation.objects.count()
    total_foods = FoodMenu.objects.count()
    total_spas = WellnessService.objects.count()
    total_products = OTOPProduct.objects.count()
    total_catalog_count = total_stays + total_foods + total_spas + total_products

    # -------------------------------------------------------------------------
    # 2. Module-Specific Data Loading
    # -------------------------------------------------------------------------
    context = {
        'page_title': 'ศูนย์ควบคุมระบบแอดมิน (Admin Command Center) — WellTrip',
        'active_tab': active_tab,
        'total_users_count': total_users_count,
        'tourists_count': tourists_count,
        'merchants_count': merchants_count,
        'total_pending_kyc': total_pending_kyc,
        'pending_slips_count': pending_slips_count,
        'total_bookings_count': total_bookings_count,
        'total_revenue': total_revenue,
        'total_catalog_count': total_catalog_count,
        'total_stays': total_stays,
        'total_foods': total_foods,
        'total_spas': total_spas,
        'total_products': total_products,
    }

    # TAB 1: OVERVIEW
    if active_tab == 'overview':
        context['recent_bookings'] = Booking.objects.select_related('customer').order_by('-created_at')[:6]
        context['pending_merchants'] = MerchantProfile.objects.filter(status=MerchantApprovalStatus.PENDING).select_related('user')[:5]
        context['pending_payments'] = Payment.objects.filter(status=PaymentStatus.PENDING).select_related('booking__customer')[:5]
        context['recent_audits'] = AuditLog.objects.select_related('user').order_by('-timestamp')[:8]

    # TAB 2: PAYMENTS (Slips)
    elif active_tab == 'payments':
        pay_status = request.GET.get('status', '').strip()
        payments_qs = Payment.objects.select_related('booking__customer').prefetch_related('slips').order_by('-created_at')
        if pay_status:
            payments_qs = payments_qs.filter(status=pay_status)
        
        paginator = Paginator(payments_qs, 20)
        context['payments_page'] = paginator.get_page(request.GET.get('page'))
        context['selected_status'] = pay_status
        context['payment_statuses'] = PaymentStatus.choices

    # TAB 3: APPROVALS (KYC)
    elif active_tab == 'approvals':
        kyc_status = request.GET.get('status', '').strip()
        profiles_qs = MerchantProfile.objects.select_related('user').order_by('-created_at')
        if kyc_status:
            profiles_qs = profiles_qs.filter(status=kyc_status)
        
        paginator = Paginator(profiles_qs, 20)
        context['profiles_page'] = paginator.get_page(request.GET.get('page'))
        context['selected_kyc_status'] = kyc_status
        context['approval_statuses'] = MerchantApprovalStatus.choices
        
        # Legacy unverified merchants
        context['legacy_merchants'] = User.objects.filter(
            role__in=[
                UserRoles.HOMESTAY_OWNER,
                UserRoles.RESTAURANT_OWNER,
                UserRoles.WELLNESS_OWNER,
                UserRoles.OTOP_OWNER,
            ],
            email_verified=False
        ).exclude(merchant_profile__isnull=False)

    # TAB 4: CATALOG
    elif active_tab == 'catalog':
        cat_type = request.GET.get('type', 'all').strip()
        context['cat_type'] = cat_type
        context['accommodations'] = Accommodation.objects.select_related('owner').order_by('-created_at')[:30]
        context['foods'] = FoodMenu.objects.select_related('owner').order_by('-created_at')[:30]
        context['spas'] = WellnessService.objects.select_related('owner').order_by('-created_at')[:30]
        context['products'] = OTOPProduct.objects.select_related('owner').order_by('-created_at')[:30]

    # TAB 5: USERS
    elif active_tab == 'users':
        query = request.GET.get('q', '').strip()
        role_filter = request.GET.get('role', '').strip()
        users_qs = User.objects.all().order_by('-date_joined')
        if query:
            users_qs = users_qs.filter(
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(phone_number__icontains=query)
            )
        if role_filter:
            users_qs = users_qs.filter(role=role_filter)
        paginator = Paginator(users_qs, 25)
        context['users_page'] = paginator.get_page(request.GET.get('page'))
        context['user_query'] = query
        context['user_role_filter'] = role_filter
        context['role_choices'] = UserRoles.choices

    # TAB 6: LOCATIONS & PASSPORT
    elif active_tab == 'locations':
        context['map_locations'] = MapLocation.objects.all().order_by('title')
        context['location_events'] = LocationEvent.objects.select_related('user').order_by('-created_at')[:30]
        context['passport_stamps'] = PassportStamp.objects.select_related('user').order_by('-stamped_at')[:30]

    # TAB 7: CONTENT / STORIES
    elif active_tab == 'content':
        context['stories'] = EditorialEntry.objects.all().order_by('-updated_at')

    return render(request, 'admin/dashboard.html', context)


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_approvals_view(request):
    """Legacy redirect to unified command center tab."""
    return redirect('/accounts/admin-center/?tab=approvals')



@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_approve_merchant_view(request, user_id):
    """
    One-Time Merchant Approval Action:
    Approves the merchant once, automatically activating their account,
    updating MerchantProfile, switching homestay listings to ACTIVE, and dispatching notification.
    """
    merchant = get_object_or_404(User, id=user_id)

    with transaction.atomic():
        merchant.email_verified = True
        merchant.is_active = True
        merchant.save(update_fields=['email_verified', 'is_active'])

        MerchantProfile.objects.filter(user=merchant).update(
            status=MerchantApprovalStatus.APPROVED,
            reviewed_at=timezone.now(),
            rejection_reason=""
        )

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
    return redirect('/accounts/admin-center/?tab=approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_reject_merchant_view(request, user_id):
    """
    Merchant KYC Rejection Action:
    Marks rejection, updates MerchantProfile with reason, and dispatches explanation email.
    """
    merchant = get_object_or_404(User, id=user_id)
    reason = request.POST.get('reason', '').strip() or "ข้อมูลเอกสารประกอบการยืนยันตัวตนไม่ครบถ้วนหรือไม่สอดคล้องตามเกณฑ์มาตรฐาน"

    with transaction.atomic():
        MerchantProfile.objects.filter(user=merchant).update(
            status=MerchantApprovalStatus.REJECTED,
            reviewed_at=timezone.now(),
            rejection_reason=reason
        )

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
    return redirect('/accounts/admin-center/?tab=approvals')


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
