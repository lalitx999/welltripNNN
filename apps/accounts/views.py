from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import EmailOTPForm, LoginForm, UserRegistrationForm, MerchantRegistrationForm
from apps.accounts.models import User, UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services import email_verification_service, google_auth_service
from apps.accounts.services.audit import record_audit_log, get_client_ip
from django.utils.translation import gettext as _

PENDING_VERIFICATION_SESSION_KEY = 'pending_verification_user_id'
GOOGLE_FLOW_SESSION_KEY = 'google_oauth_flow'


def _is_safe_next_url(request, next_url):
    # Reject //evil.com and other off-site targets (open redirect)
    return next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )


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

            # Right password, but no session until the mailbox is proven too
            if user.needs_email_verification:
                _begin_email_verification(request, user)
                return redirect('accounts:verify_email')

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

            messages.success(request, _("ยินดีต้อนรับ {value}").format(value=user.first_name or user.email))

            next_url = request.GET.get('next')
            if _is_safe_next_url(request, next_url):
                return redirect(next_url)

            return redirect_after_auth(user)
        else:
            messages.error(request, _("การเข้าสู่ระบบไม่สำเร็จ กรุณาตรวจสอบอีเมลและรหัสผ่าน"))

    return render(request, 'accounts/login.html', {
        'form': form,
        'google_login_enabled': google_auth_service.is_enabled(),
    })


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Secure Registration View:
    1. Rate limited to 3 registrations/hour per IP.
    2. ModelForm validation with password complexity enforcement.
    3. AuditLog creation, then email OTP verification before the first login.
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

            _begin_email_verification(request, user)
            return redirect('accounts:verify_email')
        else:
            messages.error(request, _("ข้อมูลการสมัครสมาชิกไม่ถูกต้อง กรุณาตรวจสอบข้อผิดพลาดด้านล่าง"))

    return render(request, 'accounts/register.html', {
        'form': form,
        'google_login_enabled': google_auth_service.is_enabled(),
    })


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

            _begin_email_verification(request, user)
            return redirect('accounts:verify_email')
        else:
            messages.error(request, _("ข้อมูลการลงทะเบียนผู้ประกอบการไม่ถูกต้อง กรุณาตรวจสอบข้อผิดพลาดด้านล่าง"))

    return render(request, 'accounts/register_merchant.html', {'form': form})


def _begin_email_verification(request, user):
    """Remember who is verifying server-side and email them a code."""
    request.session[PENDING_VERIFICATION_SESSION_KEY] = str(user.id)
    sent, message = email_verification_service.send_verification_code(user)
    (messages.success if sent else messages.warning)(request, message)


def _get_pending_verification_user(request):
    user_id = request.session.get(PENDING_VERIFICATION_SESSION_KEY)
    if not user_id:
        return None
    user = User.objects.filter(pk=user_id, is_active=True).first()
    return user if user and user.needs_email_verification else None


@ratelimit(key='ip', rate='20/m', method=['POST'], block=True)
@require_http_methods(["GET", "POST"])
def verify_email_view(request):
    """Second step of sign-up: a correct OTP verifies the email and starts the session."""
    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    user = _get_pending_verification_user(request)
    if user is None:
        return redirect('accounts:login')

    form = EmailOTPForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        verified, message = email_verification_service.confirm_verification_code(
            user, form.cleaned_data['code']
        )
        if verified:
            request.session.pop(PENDING_VERIFICATION_SESSION_KEY, None)

            record_audit_log(
                request=request,
                action="EMAIL_VERIFIED",
                model_name="User",
                object_id=str(user.id),
                changes={"email": user.email},
                user=user,
            )

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session.cycle_key()

            if user.is_merchant:
                messages.success(request, _("ยืนยันอีเมลสำเร็จ คำขอเปิดร้านของคุณอยู่ระหว่างการตรวจสอบโดยผู้ดูแลระบบ"))
            else:
                messages.success(request, _("ยืนยันอีเมลสำเร็จ ยินดีต้อนรับสู่ WellTrip"))
            return redirect_after_auth(user)
        form.add_error('code', message)

    return render(request, 'accounts/verify_email.html', {'form': form, 'pending_email': user.email})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
@require_http_methods(["POST"])
def resend_verification_view(request):
    user = _get_pending_verification_user(request)
    if user is None:
        return redirect('accounts:login')

    sent, message = email_verification_service.send_verification_code(user)
    (messages.success if sent else messages.warning)(request, message)
    return redirect('accounts:verify_email')


@ratelimit(key='ip', rate='20/m', method=['GET'], block=True)
@require_http_methods(["GET"])
def google_login_view(request):
    """Send the visitor to Google, keeping the anti-forgery values in their session."""
    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    if not google_auth_service.is_enabled():
        messages.error(request, _("ยังไม่เปิดให้เข้าสู่ระบบด้วย Google"))
        return redirect('accounts:login')

    canonical_url = google_auth_service.canonical_login_url(request)
    if canonical_url:
        return redirect(canonical_url)

    authorization_url, flow = google_auth_service.begin_login()
    flow['next'] = request.GET.get('next', '')
    request.session[GOOGLE_FLOW_SESSION_KEY] = flow
    return redirect(authorization_url)


@ratelimit(key='ip', rate='20/m', method=['GET'], block=True)
@require_http_methods(["GET"])
def google_callback_view(request):
    """
    Google's redirect back. The state is single-use and tied to this browser's session,
    so a forged link cannot sign a visitor in to someone else's account.
    The token exchange stays in the request: the login cannot finish without its answer.
    """
    flow = request.session.pop(GOOGLE_FLOW_SESSION_KEY, None)

    if request.user.is_authenticated:
        return redirect_after_auth(request.user)

    if not flow or not constant_time_compare(request.GET.get('state', ''), flow['state']):
        messages.error(request, _("เซสชันเข้าสู่ระบบด้วย Google หมดอายุ กรุณาลองใหม่อีกครั้ง"))
        return redirect('accounts:login')

    code = request.GET.get('code')
    if not code:
        messages.info(request, _("ยกเลิกการเข้าสู่ระบบด้วย Google แล้ว"))
        return redirect('accounts:login')

    try:
        claims = google_auth_service.fetch_identity(code, flow)
        user, created = google_auth_service.get_or_create_user(claims)
    except google_auth_service.GoogleAuthError as exc:
        messages.error(request, str(exc))
        return redirect('accounts:login')

    request.session.pop(PENDING_VERIFICATION_SESSION_KEY, None)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.cycle_key()

    user.last_login_ip = get_client_ip(request)
    user.save(update_fields=['last_login_ip', 'last_login'])

    record_audit_log(
        request=request,
        action="REGISTER_GOOGLE" if created else "LOGIN_GOOGLE",
        model_name="User",
        object_id=str(user.id),
        changes={"email": user.email, "role": user.role},
        user=user,
    )

    messages.success(request, _("ยินดีต้อนรับ {value}").format(value=user.first_name or user.email))

    if _is_safe_next_url(request, flow.get('next')):
        return redirect(flow['next'])
    return redirect_after_auth(user)


# POST only: a GET logout lets any page sign visitors out via a link or <img> (CSRF)
@require_http_methods(["POST"])
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
    messages.success(request, _("ออกจากระบบเรียบร้อยแล้ว"))
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
    """Partner Studio landing page with the merchant's real listing and order figures."""
    from apps.accommodations.models import Accommodation
    from apps.bookings.models import BookingItem, BookingStatus
    from apps.otop.models import OTOPProduct
    from apps.services.models import FoodMenu, WellnessService

    user = request.user
    listing_counts = {
        UserRoles.HOMESTAY_OWNER: lambda: Accommodation.objects.filter(owner=user).count(),
        UserRoles.RESTAURANT_OWNER: lambda: FoodMenu.objects.filter(owner=user).count(),
        UserRoles.WELLNESS_OWNER: lambda: WellnessService.objects.filter(owner=user).count(),
        UserRoles.OTOP_OWNER: lambda: OTOPProduct.objects.filter(owner=user).count(),
    }
    vendor_items = BookingItem.objects.filter(vendor=user).select_related('booking')
    return render(request, 'accounts/portal_dashboard.html', {
        'page_title': _("Partner Studio - ภาพรวมธุรกิจชุมชน"),
        'listing_count': listing_counts.get(user.role, lambda: 0)(),
        'awaiting_count': vendor_items.filter(booking__status=BookingStatus.AWAITING_PAYMENT).count(),
        'confirmed_count': vendor_items.filter(booking__status=BookingStatus.CONFIRMED).count(),
        'recent_items': vendor_items.order_by('-booking__created_at')[:8],
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
        messages.success(request, _("บันทึกข้อมูลโปรไฟล์เรียบร้อยแล้ว"))
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
        'page_title': _("โปรไฟล์ส่วนตัว — WellTrip"),
        'total_bookings_count': total_bookings_count,
        'active_bookings_count': active_bookings_count,
        'stamps_count': stamps_count,
        'merchant_profile': merchant_profile,
    })

