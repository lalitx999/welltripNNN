"""
Visitor counter.

Counts page views of public HTML pages and unique visitors per day. A visitor is
recognised by a hash of the day, IP address and browser, kept only in the cache
until the end of that day, so nothing that identifies a person is stored and a
visitor cannot be followed from one day to the next. The cache is Redis in
production, shared by all Gunicorn workers.
"""
import hashlib
import logging
import re
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.accounts.services.audit import get_client_ip
from apps.core.models import DailyVisitStat

logger = logging.getLogger(__name__)

# Pages for staff and partners, files, and endpoints that are not page visits
EXCLUDED_PREFIXES = (
    "/static/", "/media/", "/i18n/", "/admin/",
    "/accounts/admin", "/accounts/portal/",
    "/favicon", "/robots.txt", "/sitemap", "/llm", "/offline/", "/sw.js",
)

BOT_PATTERN = re.compile(
    r"bot|crawl|spider|slurp|preview|scan|monitor|curl|wget|python|httpx|okhttp|"
    r"go-http|java/|headless|lighthouse|facebookexternalhit|whatsapp|line-poker",
    re.IGNORECASE,
)


def should_count(request, response) -> bool:
    """True for a successful GET of a public HTML page by a person."""
    if request.method != "GET" or response.status_code != 200:
        return False
    if not response.get("Content-Type", "").startswith("text/html"):
        return False
    if request.headers.get("X-Requested-With") or request.headers.get("HX-Request"):
        return False
    # Browsers mark a page the person opens as "navigate"; the service worker
    # pre-loading /offline/ and other fetches use other modes
    fetch_mode = request.headers.get("Sec-Fetch-Mode")
    if fetch_mode and fetch_mode != "navigate":
        return False
    if request.path.startswith(EXCLUDED_PREFIXES):
        return False
    user_agent = request.headers.get("User-Agent", "")
    if not user_agent or BOT_PATTERN.search(user_agent):
        return False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and (user.is_staff or getattr(user, "is_community_admin", False)):
        return False
    return True


def _is_first_visit_today(request, today) -> bool:
    raw = f"{settings.SECRET_KEY}|{today.isoformat()}|{get_client_ip(request)}|{request.headers.get('User-Agent', '')}"
    key = "visit:" + hashlib.sha256(raw.encode()).hexdigest()
    tomorrow = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    ttl = max(60, int((tomorrow - timezone.now()).total_seconds()) + 60)
    return cache.add(key, 1, timeout=ttl)


def record_visit(request) -> None:
    today = timezone.localdate()
    new_visitor = 1 if _is_first_visit_today(request, today) else 0
    changes = {"page_views": F("page_views") + 1, "visitors": F("visitors") + new_visitor}
    if DailyVisitStat.objects.filter(date=today).update(**changes):
        return
    try:
        with transaction.atomic():
            DailyVisitStat.objects.create(date=today, page_views=1, visitors=new_visitor)
    except IntegrityError:
        # Another worker created today's row first
        DailyVisitStat.objects.filter(date=today).update(**changes)


def count_visit(request, response) -> None:
    """Never lets counting break the page."""
    try:
        if should_count(request, response):
            record_visit(request)
    except DatabaseError:
        logger.exception("Could not record a site visit")


def visit_summary(days: int = 14) -> dict:
    """Totals for the admin dashboard plus one entry per day for the last `days` days."""
    today = timezone.localdate()

    def totals(since=None):
        qs = DailyVisitStat.objects.all()
        if since:
            qs = qs.filter(date__gte=since)
        result = qs.aggregate(visitors=Sum("visitors"), page_views=Sum("page_views"))
        return {k: v or 0 for k, v in result.items()}

    start = today - timedelta(days=days - 1)
    by_date = {s.date: s for s in DailyVisitStat.objects.filter(date__gte=start)}
    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        stat = by_date.get(day)
        series.append({"date": day, "visitors": stat.visitors if stat else 0})
    peak = max((d["visitors"] for d in series), default=0) or 1
    for d in series:
        d["percent"] = round(d["visitors"] * 100 / peak)

    return {
        "today": totals(today),
        "last_7_days": totals(today - timedelta(days=6)),
        "last_30_days": totals(today - timedelta(days=29)),
        "all_time": totals(),
        "series": series,
    }
