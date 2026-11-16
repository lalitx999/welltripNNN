"""
Coordinates from what admins and partners paste: Google Maps links or "lat, lng".

A Google Maps place link holds two pairs of numbers:
    .../place/Name/@14.6201,104.4150,17z/data=!3m1!4b1!4m6!3m5!1s...!8m2!3d14.6184595!4d104.4193077
"@lat,lng" is only where the map view was centred when the link was copied; the
place's own pin is "!3d<lat>!4d<lng>". Reading "@" first put pins tens to hundreds
of metres off, so the pin pair always wins here.

Short share links (maps.app.goo.gl/...) carry no numbers; they are expanded by
following Google's redirect (Google hosts only) before parsing.
"""
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

NUM = r"(-?\d{1,3}\.\d+)"
PATTERNS = [
    re.compile(rf"!3d{NUM}!4d{NUM}"),  # the place pin
    re.compile(rf"[?&](?:q|ll|query|destination|center)={NUM},\s*{NUM}"),
    re.compile(rf"/place/{NUM},\s*{NUM}"),
    re.compile(rf"/search/{NUM},\s*\+?{NUM}"),
    re.compile(rf"@{NUM},{NUM}"),  # map centre: last resort
    re.compile(rf"^\s*{NUM}\s*[,\s]\s*{NUM}\s*$"),  # "15.1186, 104.3225"
]
SHORT_LINK_HOSTS = {"maps.app.goo.gl", "goo.gl", "g.co"}
PLACES = Decimal("0.0000001")


def _valid(lat, lng):
    return -90 <= lat <= 90 and -180 <= lng <= 180


def parse_coordinates(text):
    """(Decimal lat, Decimal lng) found in a link or "lat, lng" text, else (None, None)."""
    if not text:
        return None, None
    s = unquote(str(text).strip())
    for pattern in PATTERNS:
        m = pattern.search(s)
        if not m:
            continue
        try:
            lat, lng = Decimal(m.group(1)), Decimal(m.group(2))
        except InvalidOperation:
            continue
        if _valid(lat, lng):
            return lat.quantize(PLACES), lng.quantize(PLACES)
    return None, None


def expand_short_link(url, timeout=5):
    """Follow a maps.app.goo.gl style link to the full Google Maps URL; other hosts are left alone."""
    try:
        host = (urlparse(str(url).strip()).hostname or "").lower()
    except ValueError:
        return url
    if host not in SHORT_LINK_HOSTS:
        return url
    try:
        import requests
        response = requests.get(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        final_host = (urlparse(response.url).hostname or "").lower()
        if final_host.endswith("google.com") or final_host.endswith("google.co.th"):
            return response.url
    except Exception as exc:
        logger.info("Could not expand map link %s: %s", url, exc)
    return url


def coordinates_from_maps_input(text):
    """Parse coordinates, expanding a Google short link first when there are none in the text."""
    lat, lng = parse_coordinates(text)
    if lat is None and text:
        lat, lng = parse_coordinates(expand_short_link(text))
    return lat, lng
