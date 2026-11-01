from datetime import date
from itertools import groupby

from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.community.models import Event

# Columns the public cards and calendar actually render
_CARD_FIELDS = (
    "id", "title", "title_en", "category", "summary", "summary_en",
    "start_date", "end_date", "date_note", "date_note_en",
    "venue", "venue_en", "image",
)


def _public_events(today=None):
    today = today or timezone.localdate()
    return Event.objects.filter(is_published=True, end_date__gte=today)


def upcoming_events(limit=4, today=None):
    """Published events that have not ended yet, soonest first (homepage strip)."""
    return list(_public_events(today).only(*_CARD_FIELDS).order_by("start_date", "title")[:limit])


def events_by_month(category=None, today=None):
    """[(first day of month, [events...]), ...] for the calendar page."""
    qs = _public_events(today).only(*_CARD_FIELDS).order_by("start_date", "title")
    if category:
        qs = qs.filter(category=category)
    return [
        (month, list(items))
        for month, items in groupby(qs, key=lambda e: date(e.start_date.year, e.start_date.month, 1))
    ]


def get_public_event(event_id):
    return get_object_or_404(
        Event.objects.select_related("check_in_point"), id=event_id, is_published=True
    )


def admin_event_list():
    return Event.objects.select_related("check_in_point").order_by("-start_date")
