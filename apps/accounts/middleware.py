import time
from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect


class SessionIdleTimeoutMiddleware:
    """
    Enforces a strict 30-minute idle session timeout (Security Requirement #1).
    If an authenticated user has been inactive for longer than SESSION_IDLE_TIMEOUT,
    the session is flushed, the user is logged out, and redirected to login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_time = int(time.time())
            last_activity = request.session.get('last_activity')

            idle_timeout = getattr(settings, 'SESSION_IDLE_TIMEOUT', 1800)  # 30 minutes default

            if last_activity and (current_time - last_activity > idle_timeout):
                # Session has been idle too long
                logout(request)
                request.session.flush()
                messages.warning(request, "เซสชันของคุณหมดอายุเนื่องจากไม่มีการใช้งานเกิน 30 นาที กรุณาเข้าสู่ระบบใหม่")
                return redirect('accounts:login')

            # Update last activity timestamp on active requests
            request.session['last_activity'] = current_time

        return self.get_response(request)
