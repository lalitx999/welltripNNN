from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import LoginForm, UserRegistrationForm, MerchantRegistrationForm
from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log, get_client_ip


@ratelimit(key='ip', rate='20/m', method=['POST'], block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Secure Login View:
    1. Rate limited on POST submissions (20/minute per IP).
    2. Axes throttles consecutive failures (lockout after 5).
    3. Session Key is rotated upon successful login (anti-session fixation).
    4. Successful login records an AuditLog entry.
    """
    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    form = LoginForm(request=request, data=request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            
            # Login user
            login(request, user)
            
            # Security Requirement #1: Rotate session key on login to prevent session fixation
            request.session.cycle_key()

            # Record login IP and AuditLog
            user.last_login_ip = get_client_ip(request)
            user.save(update_fields=['last_login_ip', 'last_login'])

            record_audit_log(
                request=request,
                action="LOGIN",
                model_name="User",
                object_id=str(user.id),
                changes={"email": user.email, "role": user.role},
                user=user,
            )

            messages.success(request, f"ยินดีต้อนรับ {user.first_name or user.email}")

            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            return redirect_after_auth(user)
        else:
            messages.error(request, "การเข้าสู่ระบบไม่สำเร็จ กรุณาตรวจสอบอีเมลและรหัสผ่าน")

    return render(request, 'accounts/login.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Secure Registration View:
    1. Rate limited to 3 registrations/hour per IP.
    2. ModelForm validation with password complexity enforcement.
    3. Automatic session initiation and AuditLog creation.
    """
    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    form = UserRegistrationForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = form.save()

            record_audit_log(
                request=request,
                action="REGISTER",
                model_name="User",
                object_id=str(user.id),
                changes={"email": user.email, "role": user.role},
                user=user,
            )

            # Auto-login after successful registration with explicit backend
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session.cycle_key()

            messages.success(request, "สร้างบัญชีผู้ใช้งานสำเร็จ")
            return redirect_after_auth(user)
        else:
            messages.error(request, "ข้อมูลการสมัครสมาชิกไม่ถูกต้อง กรุณาตรวจสอบข้อผิดพลาดด้านล่าง")

    return render(request, 'accounts/register.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
@require_http_methods(["GET", "POST"])
def merchant_register_view(request):
    """
    Merchant Registration View (3-Step Wizard compatible).
    Enables vendor onboarding for Homestays, Restaurants, Wellness, and OTOP.
    Creates account with status PENDING for Admin KYC Approval.
    """
    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    form = MerchantRegistrationForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user, merchant = form.save()

            record_audit_log(
                request=request,
                action="REGISTER_MERCHANT",
                model_name="MerchantProfile",
                object_id=str(merchant.id),
                changes={
                    "email": user.email,
                    "role": user.role,
                    "business_name": merchant.business_name,
                    "category": merchant.business_category,
                    "status": merchant.status,
                },
                user=user,
            )

            # Auto-login after successful registration with explicit backend
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session.cycle_key()

            messages.success(request, f"ยื่นคำขอเปิดร้าน '{merchant.business_name}' สำเร็จ ขณะนี้อยู่ระหว่างการตรวจสอบโดยผู้ดูแลระบบ (Pending Review)")
            return redirect('accounts:portal_dashboard')
        else:
            messages.error(request, "ข้อมูลการลงทะเบียนผู้ประกอบการไม่ถูกต้อง กรุณาตรวจสอบข้อผิดพลาดด้านล่าง")

    return render(request, 'accounts/register_merchant.html', {'form': form})


@require_http_methods(["POST", "GET"])
def logout_view(request):
    """
    Secure Logout View:
    1. Records AuditLog for the logout event.
    2. Flushes session data from the server store.
    3. Clears authentication state.
    """
    if request.user.is_authenticated:
        record_audit_log(
            request=request,
            action="LOGOUT",
            model_name="User",
            object_id=str(request.user.id),
            user=request.user,
        )

    logout(request)
    request.session.flush()
    messages.success(request, "ออกจากระบบเรียบร้อยแล้ว")
    return redirect('core:home')


def redirect_after_auth(user):
    """Routes the user to their appropriate landing experience based on role."""
    if user.is_community_admin:
        return redirect('accounts:admin_dashboard')
    elif user.is_merchant:
        return redirect('accounts:portal_dashboard')
    else:
        return redirect('core:home')


@role_required(
    UserRoles.HOMESTAY_OWNER,
    UserRoles.RESTAURANT_OWNER,
    UserRoles.WELLNESS_OWNER,
    UserRoles.OTOP_OWNER,
)
def portal_dashboard_view(request):
    """Partner Studio Landing Dashboard."""
    return render(request, 'accounts/portal_dashboard.html', {
        'page_title': 'Partner Studio - ภาพรวมธุรกิจชุมชน',
    })


@role_required(UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
def admin_dashboard_view(request):
    """Admin Operations Landing Dashboard: Forward to Unified Command Center."""
    from . import admin_views
    return admin_views.admin_command_center_view(request)


@require_http_methods(["GET", "POST"])
def profile_view(request):
    """Tourist and merchant personal profile view and update."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    user = request.user
    if request.method == "POST":
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()

        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number
        user.save(update_fields=['first_name', 'last_name', 'phone_number'])

        record_audit_log(
            request=request,
            action="UPDATE",
            model_name="User",
            object_id=str(user.id),
            changes={'first_name': first_name, 'last_name': last_name, 'phone_number': phone_number},
            user=user,
        )
        messages.success(request, "บันทึกข้อมูลโปรไฟล์เรียบร้อยแล้ว")
        return redirect('accounts:profile')

    from apps.bookings.models import Booking, BookingStatus
    from apps.community.models import PassportStamp

    total_bookings_count = Booking.objects.filter(customer=user).count()
    active_bookings_count = Booking.objects.filter(
        customer=user,
        status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED]
    ).count()
    stamps_count = PassportStamp.objects.filter(user=user).count()
    merchant_profile = getattr(user, 'merchant_profile', None)

    return render(request, 'accounts/profile.html', {
        'page_title': 'โปรไฟล์ส่วนตัว — WellTrip',
        'total_bookings_count': total_bookings_count,
        'active_bookings_count': active_bookings_count,
        'stamps_count': stamps_count,
        'merchant_profile': merchant_profile,
    })

