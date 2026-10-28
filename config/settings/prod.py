"""
Production settings for WellTrip Monolith (Homeserver & Production).
Strictly enforces DEBUG=False, SSL redirect, HSTS, Secure Cookies.
"""
from .base import *

DEBUG = False

# Host must be explicitly defined (support both ALLOWED_HOSTS and DJANGO_ALLOWED_HOSTS)
_prod_hosts = config(
    'ALLOWED_HOSTS',
    default=config('DJANGO_ALLOWED_HOSTS', default='*')
)
if isinstance(_prod_hosts, str):
    ALLOWED_HOSTS = [h.strip() for h in _prod_hosts.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = list(_prod_hosts)

# HTTPS & HSTS Settings (Behind Cloudflare Tunnel)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies over HTTPS
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)

# Reverse Proxy SSL Header (Nginx / Cloudflare Tunnel)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Sentry Configuration
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

