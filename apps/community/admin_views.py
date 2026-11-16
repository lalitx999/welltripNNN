"""Admin Center: event calendar management (list lives in the 'events' tab)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.community.forms import EventForm, EventGalleryForm
from apps.community.models import Event, EventImage
from apps.community.services.event_service import (
    add_gallery_images, delete_event, delete_gallery_image, save_event,
)
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
        **(_gallery_context(event) if event_id else {}),
    })


def _gallery_context(event, gallery_form=None):
    photos = list(event.gallery.all())
    room_left = EventImage.MAX_PER_EVENT - len(photos)
    return {
        "gallery": photos,
        "gallery_room_left": room_left,
        "gallery_max": EventImage.MAX_PER_EVENT,
        "gallery_form": gallery_form or EventGalleryForm(room_left=room_left),
    }


@role_required(*ADMIN_ROLES)
@require_POST
def event_gallery_add_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    room_left = EventImage.MAX_PER_EVENT - event.gallery.count()
    form = EventGalleryForm(request.POST, request.FILES, room_left=room_left)
    if form.is_valid():
        added = add_gallery_images(request, event, form.cleaned_data["images"])
        messages.success(request, _("เพิ่มรูปในแกลเลอรี {count} รูปแล้ว").format(count=len(added)))
    else:
        messages.error(request, " ".join(form.errors.get("images", [_("รูปภาพไม่ถูกต้อง")])))
    return redirect("accounts:admin_event_edit", event_id=event.id)


@role_required(*ADMIN_ROLES)
@require_POST
def event_gallery_delete_view(request, photo_id):
    photo = get_object_or_404(EventImage.objects.select_related("event"), id=photo_id)
    event_id = photo.event_id
    delete_gallery_image(request, photo)
    messages.success(request, _("ลบรูปออกจากแกลเลอรีแล้ว"))
    return redirect("accounts:admin_event_edit", event_id=event_id)


@role_required(*ADMIN_ROLES)
@require_POST
def event_delete_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    title = event.title
    delete_event(request, event)
    messages.success(request, _("ลบกิจกรรม \"{title}\" แล้ว").format(title=title))
    return redirect(EVENTS_TAB)
