from datetime import timedelta
from urllib.parse import urlencode

from django.db import transaction

from apps.accounts.services.audit import record_audit_log


@transaction.atomic
def save_event(request, form):
    """Persist an EventForm and audit who changed what."""
    is_new = form.instance._state.adding
    event = form.save()
    record_audit_log(
        request=request,
        action="CREATE" if is_new else "UPDATE",
        model_name="Event",
        object_id=str(event.id),
        changes={
            "title": event.title,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "is_published": event.is_published,
        },
        user=request.user,
    )
    return event


@transaction.atomic
def delete_event(request, event):
    record_audit_log(
        request=request,
        action="DELETE",
        model_name="Event",
        object_id=str(event.id),
        changes={"title": event.title},
        user=request.user,
    )
    files = [photo.image for photo in event.gallery.all()]
    if event.image:
        files.append(event.image)
    event.delete()
    transaction.on_commit(lambda: [f.delete(save=False) for f in files])


def google_calendar_url(event, title, venue):
    """'Add to Google Calendar' link for an all-day event (end date is exclusive)."""
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{event.start_date:%Y%m%d}/{event.end_date + timedelta(days=1):%Y%m%d}",
        "location": venue,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


@transaction.atomic
def add_gallery_images(request, event, images):
    """Append sanitized photos to the end of an event's gallery."""
    from apps.community.models import EventImage

    start = event.gallery.count()
    created = [
        EventImage.objects.create(event=event, image=image, order=start + offset)
        for offset, image in enumerate(images)
    ]
    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="Event",
        object_id=str(event.id),
        changes={"gallery_added": len(created)},
        user=request.user,
    )
    return created


@transaction.atomic
def delete_gallery_image(request, photo):
    event = photo.event
    record_audit_log(
        request=request,
        action="UPDATE",
        model_name="Event",
        object_id=str(event.id),
        changes={"gallery_removed": photo.id},
        user=request.user,
    )
    file = photo.image
    photo.delete()
    transaction.on_commit(lambda: file.delete(save=False))
