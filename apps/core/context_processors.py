import os

from django.conf import settings

# Cache-busting token for our own CSS/JS: nginx caches /static/ for 30 days and
# filenames are not hashed, so the URL must change whenever the file changes.
_THEME_CSS = os.path.join(settings.BASE_DIR, 'static', 'css', 'welltrip.css')


def asset_version(request):
    try:
        version = str(int(os.path.getmtime(_THEME_CSS)))
    except OSError:
        version = '1'
    return {'asset_version': version}
