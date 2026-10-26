from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import LoginForm, UserRegistrationForm
from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log, get_client_ip


@ratelimit(key='ip', rate='5/m', block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Secure Login View:
    1. Rate limited to 5 requests/minute per IP (django-ratelimit).
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


@ratelimit(key='ip', rate='3/h', block=True)
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

            # Auto-login after successful registration
            login(request, user)
            request.session.cycle_key()

            messages.success(request, "สร้างบัญชีผู้ใช้งานสำเร็จ")
            return redirect_after_auth(user)
        else:
            messages.error(request, "ข้อมูลการสมัครสมาชิกไม่ถูกต้อง กรุณาตรวจสอบข้อผิดพลาดด้านล่าง")

    return render(request, 'accounts/register.html', {'form': form})


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
    """Admin Operations Landing Dashboard."""
    return render(request, 'accounts/admin_dashboard.html', {
        'page_title': 'ศูนย์ปฏิบัติการชุมชน (Admin Operations)',
    })
