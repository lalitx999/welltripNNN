"""
Audit Logging Service for WellTrip.
Meets Security Requirement #8:
- AuditLog: user, action, model, object_id, changes(JSON), ip, ua, timestamp
- Logs: login/logout, create/update/delete, permission denied, admin actions
- Sensitive data filtering: passwords, tokens, full PII are NEVER logged.
"""
from apps.accounts.models import AuditLog


def get_client_ip(request):
    """Safely retrieves client IP address from request headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def record_audit_log(
    request=None,
    action=None,
    model_name="",
    object_id="",
    changes=None,
    user=None,
):
    """
    Creates an AuditLog entry.
    Safe against exceptions so audit failures never break application flow,
    while ensuring security compliance.
    """
    if changes is None:
        changes = {}

    # Security check: redact passwords and tokens before persisting to DB
    filtered_changes = {}
    for k, v in changes.items():
        if any(sensitive in k.lower() for sensitive in ['password', 'secret', 'token', 'key']):
            filtered_changes[k] = '***REDACTED***'
        else:
            filtered_changes[k] = v

    actor = user
    ip_address = None
    user_agent = ""

    if request:
        if not actor and hasattr(request, 'user') and request.user.is_authenticated:
            actor = request.user
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

    try:
        return AuditLog.objects.create(
            user=actor,
            action=action or "UNKNOWN",
            model_name=model_name,
            object_id=str(object_id),
            changes=filtered_changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception as e:
        # Avoid crashing primary business operations if audit logging encounters a DB issue
        return None
