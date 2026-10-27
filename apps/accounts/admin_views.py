import re
import uuid
from decimal import Decimal
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
from apps.community.models import MapLocation, MapLocationCategory, PassportStamp, LocationEvent, EditorialEntry
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


# ==============================================================================
# FULL ADMIN CRUD: 1. CATALOG (ACCOMMODATIONS, FOODS, SPAS, OTOP)
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_catalog_add_view(request):
    """Admin creates a new catalog item across 4 categories."""
    item_type = request.POST.get('item_type', '').strip().upper()
    owner_id = request.POST.get('owner_id')
    owner = User.objects.filter(id=owner_id).first() if owner_id else request.user

    title = request.POST.get('title', '').strip()
    price_val = request.POST.get('price', '0').strip()
    description = request.POST.get('description', '').strip()
    image_file = request.FILES.get('image')

    try:
        price = Decimal(price_val)
    except Exception:
        price = Decimal("100.00")

    if not title:
        messages.error(request, "กรุณาระบุชื่อรายการ")
        return redirect('/accounts/admin-center/?tab=catalog')

    try:
        with transaction.atomic():
            if item_type == "ACCOMMODATION":
                district = request.POST.get('district', 'เมืองศรีสะเกษ').strip()
                address = request.POST.get('address', '').strip()
                acc = Accommodation.objects.create(
                    owner=owner,
                    name=title,
                    description=description,
                    address=address,
                    district=district,
                    status=AccommodationStatus.ACTIVE,
                )
                from apps.accommodations.models import Room
                room = Room.objects.create(
                    accommodation=acc,
                    name="ห้องพักมาตรฐาน",
                    base_price_per_night=price,
                    capacity_people=2,
                    total_rooms_count=5,
                    is_active=True,
                )
                if image_file:
                    from apps.accommodations.models import RoomImage
                    RoomImage.objects.create(room=room, image=image_file, is_cover=True)
                created_id = str(acc.id)

            elif item_type == "FOOD":
                wellness_cat = request.POST.get('wellness_category', 'ORGANIC')
                calorie = request.POST.get('calorie_estimate') or None
                food = FoodMenu.objects.create(
                    owner=owner,
                    name=title,
                    price=price,
                    description=description,
                    wellness_category=wellness_cat,
                    calorie_estimate=int(calorie) if calorie else None,
                    image=image_file,
                    is_available=True,
                )
                created_id = str(food.id)

            elif item_type == "WELLNESS":
                duration = request.POST.get('duration_minutes', '60')
                spa = WellnessService.objects.create(
                    owner=owner,
                    name=title,
                    price=price,
                    description=description,
                    duration_minutes=int(duration) if duration.isdigit() else 60,
                    image=image_file,
                    is_active=True,
                )
                created_id = str(spa.id)

            elif item_type == "OTOP":
                category = request.POST.get('category', 'HERBAL_PRODUCT')
                stock = request.POST.get('stock_quantity', '10')
                otop = OTOPProduct.objects.create(
                    owner=owner,
                    name=title,
                    price=price,
                    category=category,
                    stock_quantity=int(stock) if stock.isdigit() else 10,
                    description=description,
                    image=image_file,
                    is_active=True,
                )
                created_id = str(otop.id)

            else:
                messages.error(request, f"ไม่พบประเภทแคตตาล็อก: {item_type}")
                return redirect('/accounts/admin-center/?tab=catalog')

            record_audit_log(
                request=request,
                action="CREATE",
                model_name=item_type.capitalize(),
                object_id=created_id,
                changes={"title": title, "price": str(price), "created_by": request.user.email},
                user=request.user,
            )
            messages.success(request, f"เพิ่มรายการ [{item_type}] '{title}' สำเร็จ")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการเพิ่มรายการ: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=catalog')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_catalog_edit_view(request, item_type, item_id):
    """Admin updates any catalog item."""
    item_type = item_type.upper()
    title = request.POST.get('title', '').strip()
    price_val = request.POST.get('price', '').strip()
    description = request.POST.get('description', '').strip()
    raw_active = request.POST.get('is_active') or request.POST.get('is_available')
    is_active_val = str(raw_active).lower() in ('1', 'true', 'on')
    image_file = request.FILES.get('image')

    try:
        with transaction.atomic():
            if item_type == "ACCOMMODATION":
                item = get_object_or_404(Accommodation, id=item_id)
                if title:
                    item.name = title
                item.description = description
                item.status = AccommodationStatus.ACTIVE if is_active_val else AccommodationStatus.SUSPENDED
                item.save()
                if price_val:
                    first_room = item.rooms.first()
                    if first_room:
                        first_room.base_price_per_night = Decimal(price_val)
                        first_room.save(update_fields=['base_price_per_night'])

            elif item_type == "FOOD":
                item = get_object_or_404(FoodMenu, id=item_id)
                if title:
                    item.name = title
                if price_val:
                    item.price = Decimal(price_val)
                item.description = description
                item.is_available = is_active_val
                if image_file:
                    item.image = image_file
                item.save()

            elif item_type == "WELLNESS":
                item = get_object_or_404(WellnessService, id=item_id)
                if title:
                    item.name = title
                if price_val:
                    item.price = Decimal(price_val)
                item.description = description
                item.is_active = is_active_val
                if image_file:
                    item.image = image_file
                item.save()

            elif item_type == "OTOP":
                item = get_object_or_404(OTOPProduct, id=item_id)
                if title:
                    item.name = title
                if price_val:
                    item.price = Decimal(price_val)
                item.description = description
                item.is_active = is_active_val
                stock = request.POST.get('stock_quantity')
                if stock and stock.isdigit():
                    item.stock_quantity = int(stock)
                if image_file:
                    item.image = image_file
                item.save()

            else:
                messages.error(request, f"ไม่พบประเภทรายการ {item_type}")
                return redirect('/accounts/admin-center/?tab=catalog')

            record_audit_log(
                request=request,
                action="UPDATE",
                model_name=item_type.capitalize(),
                object_id=str(item_id),
                changes={"title": title, "price": price_val, "is_active": is_active_val},
                user=request.user,
            )
            messages.success(request, f"แก้ไขข้อมูล [{item_type}] สำเร็จ")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการแก้ไข: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=catalog')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_catalog_delete_view(request, item_type, item_id):
    """Admin deletes an item from catalog."""
    item_type = item_type.upper()
    try:
        with transaction.atomic():
            if item_type == "ACCOMMODATION":
                item = get_object_or_404(Accommodation, id=item_id)
            elif item_type == "FOOD":
                item = get_object_or_404(FoodMenu, id=item_id)
            elif item_type == "WELLNESS":
                item = get_object_or_404(WellnessService, id=item_id)
            elif item_type == "OTOP":
                item = get_object_or_404(OTOPProduct, id=item_id)
            else:
                messages.error(request, f"ไม่พบประเภทรายการ {item_type}")
                return redirect('/accounts/admin-center/?tab=catalog')

            item_name = getattr(item, 'name', str(item_id))
            item.delete()

            record_audit_log(
                request=request,
                action="DELETE",
                model_name=item_type.capitalize(),
                object_id=str(item_id),
                changes={"deleted_title": item_name},
                user=request.user,
            )
            messages.success(request, f"ลบรายการ [{item_type}] '{item_name}' เรียบร้อยแล้ว")
    except Exception as exc:
        messages.error(request, f"ไม่สามารถลบรายการได้เนื่องจากมีข้อมูลออเดอร์ผูกอยู่ ({str(exc)})")

    return redirect('/accounts/admin-center/?tab=catalog')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_catalog_toggle_view(request, item_type, item_id):
    """Toggles active/available status of a catalog item."""
    item_type = item_type.upper()
    try:
        if item_type == "ACCOMMODATION":
            item = get_object_or_404(Accommodation, id=item_id)
            item.status = AccommodationStatus.SUSPENDED if item.status == AccommodationStatus.ACTIVE else AccommodationStatus.ACTIVE
            item.save(update_fields=['status', 'updated_at'])
            is_now = (item.status == AccommodationStatus.ACTIVE)
        elif item_type == "FOOD":
            item = get_object_or_404(FoodMenu, id=item_id)
            item.is_available = not item.is_available
            item.save(update_fields=['is_available', 'updated_at'])
            is_now = item.is_available
        elif item_type == "WELLNESS":
            item = get_object_or_404(WellnessService, id=item_id)
            item.is_active = not item.is_active
            item.save(update_fields=['is_active', 'updated_at'])
            is_now = item.is_active
        elif item_type == "OTOP":
            item = get_object_or_404(OTOPProduct, id=item_id)
            item.is_active = not item.is_active
            item.save(update_fields=['is_active', 'updated_at'])
            is_now = item.is_active
        else:
            messages.error(request, "ไม่พบหมวดหมู่")
            return redirect('/accounts/admin-center/?tab=catalog')

        status_text = "เปิดให้บริการ/พร้อมขาย" if is_now else "ระงับ/ปิดบริการชั่วคราว"
        messages.success(request, f"เปลี่ยนสถานะ [{item_type}] เป็น '{status_text}' เรียบร้อยแล้ว")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาด: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=catalog')


# ==============================================================================
# FULL ADMIN CRUD: 2. PARTNERS & KYC
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_partner_add_view(request):
    """Admin manually creates a verified partner account & merchant profile."""
    email = request.POST.get('email', '').strip().lower()
    business_name = request.POST.get('business_name', '').strip()
    category = request.POST.get('business_category', 'HOMESTAY').strip()
    phone = request.POST.get('phone_number', '').strip()
    description = request.POST.get('description', '').strip()
    password = request.POST.get('password', 'WellTrip2026!').strip()

    role_map = {
        'HOMESTAY': UserRoles.HOMESTAY_OWNER,
        'RESTAURANT': UserRoles.RESTAURANT_OWNER,
        'WELLNESS': UserRoles.WELLNESS_OWNER,
        'OTOP': UserRoles.OTOP_OWNER,
    }
    role = role_map.get(category, UserRoles.HOMESTAY_OWNER)

    if not email or not business_name:
        messages.error(request, "กรุณาระบุอีเมลและชื่อสถานประกอบการ")
        return redirect('/accounts/admin-center/?tab=approvals')

    if User.objects.filter(email=email).exists():
        messages.error(request, f"อีเมล {email} มีอยู่ในระบบแล้ว")
        return redirect('/accounts/admin-center/?tab=approvals')

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                username=email.split('@')[0] + "_" + uuid.uuid4().hex[:4],
                password=password,
                role=role,
                phone_number=phone,
                email_verified=True,
                is_active=True,
            )
            MerchantProfile.objects.create(
                user=user,
                business_name=business_name,
                business_category=category,
                phone_number=phone,
                description=description,
                status=MerchantApprovalStatus.APPROVED,
            )
            record_audit_log(
                request=request,
                action="CREATE",
                model_name="MerchantProfile",
                object_id=str(user.id),
                changes={"email": email, "business_name": business_name, "category": category},
                user=request.user,
            )
            messages.success(request, f"เพิ่มพาร์ทเนอร์ '{business_name}' ({email}) เรียบร้อยแล้ว (รหัสผ่านเริ่มต้น: {password})")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการเพิ่มพาร์ทเนอร์: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_partner_edit_view(request, user_id):
    """Admin updates merchant profile info."""
    user = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(MerchantProfile, user=user)

    business_name = request.POST.get('business_name', '').strip()
    category = request.POST.get('business_category', '').strip()
    phone = request.POST.get('phone_number', '').strip()
    description = request.POST.get('description', '').strip()
    maps_url = request.POST.get('google_maps_url', '').strip()
    hours = request.POST.get('opening_hours', '').strip()

    if business_name:
        profile.business_name = business_name
    if category:
        profile.business_category = category
    profile.phone_number = phone
    profile.description = description
    profile.google_maps_url = maps_url
    profile.opening_hours = hours
    profile.save()

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="MerchantProfile",
        object_id=str(user.id),
        changes={"business_name": business_name, "phone": phone},
        user=request.user,
    )
    messages.success(request, f"แก้ไขข้อมูลพาร์ทเนอร์ '{profile.business_name}' เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=approvals')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_partner_delete_view(request, user_id):
    """Admin deletes merchant profile or soft-deletes merchant."""
    user = get_object_or_404(User, id=user_id)
    profile = MerchantProfile.objects.filter(user=user).first()
    business_name = profile.business_name if profile else user.email

    try:
        with transaction.atomic():
            if profile:
                profile.delete()
            user.is_active = False
            user.save(update_fields=['is_active'])

            record_audit_log(
                request=request,
                action="DELETE",
                model_name="MerchantProfile",
                object_id=str(user_id),
                changes={"deleted_partner": business_name},
                user=request.user,
            )
            messages.success(request, f"ลบข้อมูลพาร์ทเนอร์ '{business_name}' และระงับบัญชีเรียบร้อยแล้ว")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการลบพาร์ทเนอร์: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=approvals')


# ==============================================================================
# FULL ADMIN CRUD: 3. USERS MANAGEMENT
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_user_add_view(request):
    """Admin creates a new user account."""
    email = request.POST.get('email', '').strip().lower()
    password = request.POST.get('password', '').strip() or 'WellTrip2026!'
    role = request.POST.get('role', UserRoles.TOURIST).strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone = request.POST.get('phone_number', '').strip()

    if not email:
        messages.error(request, "กรุณาระบุอีเมลผู้ใช้งาน")
        return redirect('/accounts/admin-center/?tab=users')

    if User.objects.filter(email=email).exists():
        messages.error(request, f"อีเมล {email} มีผู้ใช้งานในระบบแล้ว")
        return redirect('/accounts/admin-center/?tab=users')

    try:
        user = User.objects.create_user(
            email=email,
            username=email.split('@')[0] + "_" + uuid.uuid4().hex[:4],
            password=password,
            role=role,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            email_verified=True,
            is_active=True,
        )
        record_audit_log(
            request=request,
            action="CREATE",
            model_name="User",
            object_id=str(user.id),
            changes={"email": email, "role": role},
            user=request.user,
        )
        messages.success(request, f"สร้างบัญชีผู้ใช้ {email} (บทบาท: {user.get_role_display()}) สำเร็จ (รหัสผ่าน: {password})")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการสร้างบัญชี: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=users')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_user_edit_view(request, user_id):
    """Admin updates user profile and role."""
    target_user = get_object_or_404(User, id=user_id)

    # Community admin cannot promote/demote super admin
    if request.user.role == UserRoles.COMMUNITY_ADMIN and target_user.role == UserRoles.SUPER_ADMIN:
        messages.error(request, "ไม่มีสิทธิ์แก้ไขบัญชี Super Admin")
        return redirect('/accounts/admin-center/?tab=users')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone = request.POST.get('phone_number', '').strip()
    role = request.POST.get('role', '').strip()

    target_user.first_name = first_name
    target_user.last_name = last_name
    target_user.phone_number = phone
    if role and role in dict(UserRoles.choices):
        target_user.role = role
    target_user.save()

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="User",
        object_id=str(user_id),
        changes={"name": f"{first_name} {last_name}", "phone": phone, "role": role},
        user=request.user,
    )
    messages.success(request, f"อัปเดตข้อมูลผู้ใช้ {target_user.email} เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=users')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_user_toggle_view(request, user_id):
    """Toggles user is_active status (Suspend / Activate)."""
    target_user = get_object_or_404(User, id=user_id)
    if request.user.id == target_user.id:
        messages.error(request, "ไม่สามารถระงับบัญชีของตนเองได้")
        return redirect('/accounts/admin-center/?tab=users')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status_str = "เปิดใช้งาน" if target_user.is_active else "ระงับการใช้งาน"
    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="User",
        object_id=str(user_id),
        changes={"is_active": target_user.is_active},
        user=request.user,
    )
    messages.success(request, f"เปลี่ยนสถานะบัญชี {target_user.email} เป็น '{status_str}' เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=users')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_user_reset_password_view(request, user_id):
    """Admin resets a user password."""
    target_user = get_object_or_404(User, id=user_id)
    new_password = request.POST.get('new_password', '').strip() or 'WellTrip2026!'

    target_user.set_password(new_password)
    target_user.save(update_fields=['password'])

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="User",
        object_id=str(user_id),
        changes={"action": "PASSWORD_RESET_BY_ADMIN"},
        user=request.user,
    )
    messages.success(request, f"รีเซ็ตรหัสผ่านสำหรับ {target_user.email} เป็น '{new_password}' เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=users')


def _parse_coords_from_google_maps(url_or_coords):
    """
    Parses latitude and longitude from Google Maps URL or raw coordinate text.
    Handles:
    - @15.1186000,104.3225000
    - q=15.1186,104.3225 or ll=15.1186,104.3225
    - Raw coords: 15.1186, 104.3225
    Returns (Decimal(lat), Decimal(lng)) or (None, None).
    """
    if not url_or_coords:
        return None, None
    s = str(url_or_coords).strip()
    
    # 1. @lat,lng
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        try:
            return Decimal(m.group(1)), Decimal(m.group(2))
        except Exception:
            pass

    # 2. q=lat,lng or ll=lat,lng
    m = re.search(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        try:
            return Decimal(m.group(1)), Decimal(m.group(2))
        except Exception:
            pass

    # 3. Raw lat, lng
    m = re.search(r'^(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)$', s)
    if m:
        try:
            return Decimal(m.group(1)), Decimal(m.group(2))
        except Exception:
            pass

    return None, None


# ==============================================================================
# FULL ADMIN CRUD: 4. LOCATIONS & CHECK-INS
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_location_add_view(request):
    """Admin creates a new community map location using Google Maps link."""
    title = request.POST.get('title', '').strip()
    category = request.POST.get('category', MapLocationCategory.PHOTO_SPOT).strip()
    google_maps_url = request.POST.get('google_maps_url', '').strip()
    address = request.POST.get('address', '').strip()

    if not title:
        messages.error(request, "กรุณาระบุชื่อจุดเช็คอิน")
        return redirect('/accounts/admin-center/?tab=locations')

    lat, lng = _parse_coords_from_google_maps(google_maps_url)
    if lat is None or lng is None:
        lat = Decimal("15.1186000")
        lng = Decimal("104.3225000")

    try:
        loc = MapLocation.objects.create(
            title=title,
            category=category,
            google_maps_url=google_maps_url,
            latitude=lat,
            longitude=lng,
            address=address,
            is_active=True,
        )
        record_audit_log(
            request=request,
            action="CREATE",
            model_name="MapLocation",
            object_id=str(loc.id),
            changes={"title": title, "category": category, "google_maps_url": google_maps_url},
            user=request.user,
        )
        messages.success(request, f"เพิ่มจุดเช็คอิน '{title}' เรียบร้อยแล้ว (QR Secret: {loc.qr_secret[:8]}...)")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการสร้างจุดเช็คอิน: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=locations')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_location_edit_view(request, location_id):
    """Admin updates location details and Google Maps link."""
    loc = get_object_or_404(MapLocation, id=location_id)
    title = request.POST.get('title', '').strip()
    category = request.POST.get('category', '').strip()
    google_maps_url = request.POST.get('google_maps_url', '').strip()
    address = request.POST.get('address', '').strip()
    is_active = request.POST.get('is_active') == '1'

    if title:
        loc.title = title
    if category:
        loc.category = category
    if google_maps_url:
        loc.google_maps_url = google_maps_url
        lat, lng = _parse_coords_from_google_maps(google_maps_url)
        if lat and lng:
            loc.latitude = lat
            loc.longitude = lng
    loc.address = address
    loc.is_active = is_active
    loc.save()

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="MapLocation",
        object_id=str(loc.id),
        changes={"title": title, "is_active": is_active, "google_maps_url": google_maps_url},
        user=request.user,
    )
    messages.success(request, f"แก้ไขจุดเช็คอิน '{loc.title}' สำเร็จ")
    return redirect('/accounts/admin-center/?tab=locations')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_location_delete_view(request, location_id):
    """Admin deletes a community map location."""
    loc = get_object_or_404(MapLocation, id=location_id)
    title = loc.title
    loc.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="MapLocation",
        object_id=str(location_id),
        changes={"title": title},
        user=request.user,
    )
    messages.success(request, f"ลบจุดเช็คอิน '{title}' เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=locations')


# ==============================================================================
# FULL ADMIN CRUD: 5. CONTENT & EDITORIAL STORIES
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_content_add_view(request):
    """Admin writes and publishes a new community story with image upload and Google Maps."""
    title = request.POST.get('title', '').strip()
    kind = request.POST.get('kind', EditorialEntry.Kind.STORY).strip()
    summary = request.POST.get('summary', '').strip()
    body = request.POST.get('body', '').strip()
    location = request.POST.get('location', '').strip()
    google_maps_url = request.POST.get('google_maps_url', '').strip()
    image_file = request.FILES.get('image')
    is_published = request.POST.get('is_published') == '1'

    if not title:
        messages.error(request, "กรุณาระบุหัวข้อเรื่องเล่า/บทความ")
        return redirect('/accounts/admin-center/?tab=content')

    lat, lng = _parse_coords_from_google_maps(google_maps_url)

    try:
        story = EditorialEntry.objects.create(
            title=title,
            kind=kind,
            summary=summary,
            body=body,
            location=location,
            google_maps_url=google_maps_url,
            latitude=lat,
            longitude=lng,
            image=image_file,
            is_published=is_published,
        )
        record_audit_log(
            request=request,
            action="CREATE",
            model_name="EditorialEntry",
            object_id=str(story.id),
            changes={"title": title, "kind": kind, "is_published": is_published, "google_maps_url": google_maps_url},
            user=request.user,
        )
        messages.success(request, f"สร้างบทความ/เรื่องเล่า '{title}' สำเร็จ")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการสร้างบทความ: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=content')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_content_edit_view(request, entry_id):
    """Admin updates an editorial story with image upload and Google Maps."""
    story = get_object_or_404(EditorialEntry, id=entry_id)
    title = request.POST.get('title', '').strip()
    kind = request.POST.get('kind', '').strip()
    summary = request.POST.get('summary', '').strip()
    body = request.POST.get('body', '').strip()
    location = request.POST.get('location', '').strip()
    google_maps_url = request.POST.get('google_maps_url', '').strip()
    image_file = request.FILES.get('image')
    is_published = request.POST.get('is_published') == '1'

    if title:
        story.title = title
    if kind:
        story.kind = kind
    story.summary = summary
    story.body = body
    story.location = location
    if google_maps_url:
        story.google_maps_url = google_maps_url
        lat, lng = _parse_coords_from_google_maps(google_maps_url)
        if lat and lng:
            story.latitude = lat
            story.longitude = lng
    if image_file:
        story.image = image_file
    story.is_published = is_published
    story.save()

    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="EditorialEntry",
        object_id=str(story.id),
        changes={"title": title, "is_published": is_published, "google_maps_url": google_maps_url},
        user=request.user,
    )
    messages.success(request, f"แก้ไขบทความ '{story.title}' สำเร็จ")
    return redirect('/accounts/admin-center/?tab=content')
    return redirect('/accounts/admin-center/?tab=content')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_content_delete_view(request, entry_id):
    """Admin deletes an editorial story."""
    story = get_object_or_404(EditorialEntry, id=entry_id)
    title = story.title
    story.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="EditorialEntry",
        object_id=str(entry_id),
        changes={"title": title},
        user=request.user,
    )
    messages.success(request, f"ลบบทความ '{title}' เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=content')


# ==============================================================================
# FULL ADMIN CRUD: 6. PAYMENTS & SLIPS
# ==============================================================================

@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_payment_edit_view(request, payment_id):
    """Admin manually updates payment status or amount note."""
    payment = get_object_or_404(Payment, id=payment_id)
    new_status = request.POST.get('status', '').strip()

    if new_status in dict(PaymentStatus.choices):
        payment.status = new_status
        payment.save(update_fields=['status', 'updated_at'])

        if new_status == PaymentStatus.SUCCESS:
            booking = payment.booking
            booking.status = BookingStatus.CONFIRMED
            booking.save(update_fields=['status', 'updated_at'])

        record_audit_log(
            request=request,
            action="UPDATE",
            model_name="Payment",
            object_id=str(payment.id),
            changes={"status": new_status, "booking_code": payment.booking.booking_code},
            user=request.user,
        )
        messages.success(request, f"อัปเดตสถานะการชำระเงินรหัส {payment.booking.booking_code} เป็น '{payment.get_status_display()}'")
    else:
        messages.error(request, "สถานะการชำระเงินไม่ถูกต้อง")

    return redirect('/accounts/admin-center/?tab=payments')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_slip_delete_view(request, slip_id):
    """Admin deletes a fraudulent, duplicate, or corrupted payment slip."""
    slip = get_object_or_404(PaymentSlip, id=slip_id)
    booking_code = slip.payment.booking.booking_code
    slip_ref = slip.provider_reference or str(slip.id)

    slip.delete()

    record_audit_log(
        request=request,
        action="DELETE",
        model_name="PaymentSlip",
        object_id=str(slip_id),
        changes={"booking_code": booking_code, "deleted_slip_ref": slip_ref},
        user=request.user,
    )
    messages.success(request, f"ลบหลักฐานสลิป ({slip_ref}) ของรายการ {booking_code} เรียบร้อยแล้ว")
    return redirect('/accounts/admin-center/?tab=payments')


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
@require_http_methods(["POST"])
def admin_payment_delete_view(request, payment_id):
    """Admin permanently deletes a payment and its associated booking transaction."""
    payment = get_object_or_404(Payment, id=payment_id)
    booking = payment.booking
    booking_code = booking.booking_code
    customer_email = booking.customer.email

    try:
        with transaction.atomic():
            payment.slips.all().delete()
            payment.delete()
            booking.delete()

            record_audit_log(
                request=request,
                action="DELETE",
                model_name="PaymentBooking",
                object_id=str(payment_id),
                changes={"booking_code": booking_code, "customer_email": customer_email},
                user=request.user,
            )
            messages.success(request, f"ลบรายการชำระเงินและคำสั่งจองรหัส {booking_code} ({customer_email}) เรียบร้อยแล้ว")
    except Exception as exc:
        messages.error(request, f"เกิดข้อผิดพลาดในการลบรายการ: {str(exc)}")

    return redirect('/accounts/admin-center/?tab=payments')


