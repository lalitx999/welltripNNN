#!/bin/sh
set -e

# The Celery worker shares this image; only the web container migrates
if [ "${SKIP_BOOTSTRAP:-0}" != "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

exec "$@"
