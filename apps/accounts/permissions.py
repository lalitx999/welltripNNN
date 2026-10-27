"""
Authorization Engine for WellTrip.
Enforces Role-Based and Row-Level Permissions (Security Requirement #2).

Pattern:
- View-level: @role_required(*roles)
- Object-level: can_view(user, obj), can_edit(user, obj), can_delete(user, obj)
- Queryset-level: get_scoped_queryset(model, user)
- Audit: Automatic recording of PERMISSION_DENIED events
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from apps.accounts.models import UserRoles
from apps.accounts.services.audit import record_audit_log


def role_required(*allowed_roles):
    """
    Decorator for views that checks whether the logged-in user has one of the allowed roles.
    If unauthorized, logs PERMISSION_DENIED to AuditLog and returns a clean 403 response.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/accounts/login/?next={request.path}")

            user_role = request.user.role

            # Super admins and Community admins generally have broad administrative access
            if request.user.is_superuser or user_role == UserRoles.SUPER_ADMIN:
                return view_func(request, *args, **kwargs)

            if user_role not in allowed_roles:
                # ⚠️ Record security alert in AuditLog
                record_audit_log(
                    request=request,
                    action="PERMISSION_DENIED",
                    model_name="ViewAccess",
                    object_id=request.path,
                    changes={
                        "required_roles": list(allowed_roles),
                        "user_role": user_role,
                        "view": view_func.__name__,
                    },
                )
                return HttpResponseForbidden("Access Denied: You do not have permission to access this resource.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


class RoleRequiredMixin:
    """Class-based view mixin for role-based authorization."""
    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")

        user_role = request.user.role
        if not request.user.is_superuser and user_role not in self.allowed_roles:
            record_audit_log(
                request=request,
                action="PERMISSION_DENIED",
                model_name="CBVAccess",
                object_id=request.path,
                changes={"required_roles": list(self.allowed_roles), "user_role": user_role},
            )
            raise PermissionDenied("Access Denied: Insufficient role permissions.")

        return super().dispatch(request, *args, **kwargs)


# ==============================================================================
# OBJECT-LEVEL & ROW-LEVEL OWNERSHIP GUARDS
# ==============================================================================

def can_view_object(user, obj):
    """Checks if the user has permission to view an object."""
    if not user.is_authenticated:
        # Check if the object has a public flag/status
        return getattr(obj, "status", None) == "ACTIVE" or getattr(obj, "is_active", False)

    if user.is_superuser or user.role in {UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN}:
        return True

    # 1. Direct ownership by owner_id or owner
    if hasattr(obj, "owner_id") and obj.owner_id == user.id:
        return True
    if hasattr(obj, "owner") and getattr(obj, "owner", None) == user:
        return True

    # 2. Direct ownership by user_id or user
    if hasattr(obj, "user_id") and obj.user_id == user.id:
        return True
    if hasattr(obj, "user") and getattr(obj, "user", None) == user:
        return True

    # 3. Customer ownership (e.g., Booking, Order)
    if hasattr(obj, "customer_id") and obj.customer_id == user.id:
        return True
    if hasattr(obj, "customer") and getattr(obj, "customer", None) == user:
        return True

    # 4. Payment ownership through associated booking
    if hasattr(obj, "booking"):
        booking = getattr(obj, "booking", None)
        if booking and (getattr(booking, "customer_id", None) == user.id or getattr(booking, "customer", None) == user):
            return True

    # 5. Vendor who has items inside this booking
    if hasattr(obj, "items") and hasattr(user, "id"):
        try:
            if obj.items.filter(vendor=user).exists():
                return True
        except Exception:
            pass

    return False


def can_edit_object(user, obj):
    """
    Checks if the user has permission to edit an object.
    Enforces strict ownership check (Anti-IDOR).
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.role in {UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN}:
        return True

    if hasattr(obj, "owner_id") and obj.owner_id == user.id:
        return True
    if hasattr(obj, "owner") and getattr(obj, "owner", None) == user:
        return True
    if hasattr(obj, "user_id") and obj.user_id == user.id:
        return True
    if hasattr(obj, "user") and getattr(obj, "user", None) == user:
        return True
    if hasattr(obj, "customer_id") and obj.customer_id == user.id:
        return True
    if hasattr(obj, "customer") and getattr(obj, "customer", None) == user:
        return True

    if hasattr(obj, "booking"):
        booking = getattr(obj, "booking", None)
        if booking and (getattr(booking, "customer_id", None) == user.id or getattr(booking, "customer", None) == user):
            return True

    return False


def can_delete_object(user, obj):
    """
    Checks if the user has permission to delete an object.
    Only superadmins or owners (under specific conditions) may delete.
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser or user.role == UserRoles.SUPER_ADMIN:
        return True

    owner_matches = False
    if hasattr(obj, "owner_id") and obj.owner_id == user.id:
        owner_matches = True
    elif hasattr(obj, "user_id") and obj.user_id == user.id:
        owner_matches = True
    elif hasattr(obj, "customer_id") and obj.customer_id == user.id:
        owner_matches = True

    if owner_matches:
        # Vendors/owners can only delete drafts or inactive items
        status = getattr(obj, "status", None)
        if status in {"DRAFT", "PENDING_VERIFICATION", None}:
            return True

    return False


def get_scoped_queryset(model_class, user, select_related=None, prefetch_related=None):
    """
    Returns a queryset scoped strictly to the user's role and ownership.
    Prevents N+1 queries via optional select_related and prefetch_related.
    """
    qs = model_class.objects.all()

    if select_related:
        qs = qs.select_related(*select_related)
    if prefetch_related:
        qs = qs.prefetch_related(*prefetch_related)

    # Admins see all
    if user.is_authenticated and (user.is_superuser or user.role in {UserRoles.SUPER_ADMIN, UserRoles.COMMUNITY_ADMIN}):
        return qs

    # For merchants and users: strictly filter by owner, customer, or user
    if hasattr(model_class, "owner"):
        return qs.filter(owner=user)
    elif hasattr(model_class, "customer"):
        return qs.filter(customer=user)
    elif hasattr(model_class, "user"):
        return qs.filter(user=user)

    return qs.none()
