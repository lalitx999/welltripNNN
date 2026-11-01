"""Admin Center: event calendar management (list lives in the 'events' tab)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.community.forms import EventForm
from apps.community.models import Event
from apps.community.services.event_service import delete_event, save_event
from django.utils.translation import gettext as _

ADMIN_ROLES = (UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
EVENTS_TAB = "/accounts/admin-center/?tab=events"


@role_required(*ADMIN_ROLES)
@require_http_methods(["GET", "POST"])
def event_form_view(request, event_id=None):
    event = get_object_or_404(Event, id=event_id) if event_id else Event()
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        saved = save_event(request, form)
        messages.success(request, _("บันทึกกิจกรรม \"{title}\" แล้ว").format(title=saved.title))
        return redirect(EVENTS_TAB)
    return render(request, "admin/event_form.html", {
        "form": form,
        "event": event if event_id else None,
        "active_tab": "events",
    })


@role_required(*ADMIN_ROLES)
@require_POST
def event_delete_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    title = event.title
    delete_event(request, event)
    messages.success(request, _("ลบกิจกรรม \"{title}\" แล้ว").format(title=title))
    return redirect(EVENTS_TAB)
