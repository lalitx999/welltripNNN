"""
Production settings for WellTrip Monolith (Homeserver & Production).
Strictly enforces DEBUG=False, SSL redirect, HSTS, Secure Cookies.
"""
from .base import *

DEBUG = False

# Host must be explicitly defined
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# HTTPS & HSTS Settings
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies over HTTPS only
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Reverse Proxy SSL Header (Nginx / Cloudflare)
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
        send_default_pii=False,  # ⚠️ Never send PII to Sentry
    )
