"""
Django base settings for WellTrip Monolith.
Built with strict OWASP Top 10 security standards & Bank-Grade configurations.
"""
from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Secrets & Core Settings
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production-welltrip-secret-key-1234567890')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'axes',           # Login rate-limiting & brute-force defense
    'csp',            # Content Security Policy headers
]

LOCAL_APPS = [
    'apps.accounts.apps.AccountsConfig',
    'apps.accommodations.apps.AccommodationsConfig',
    'apps.services.apps.ServicesConfig',
    'apps.otop.apps.OtopConfig',
    'apps.bookings.apps.BookingsConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.community.apps.CommunityConfig',
    'apps.ai_recommendations.apps.AiRecommendationsConfig',
    'apps.core.apps.CoreConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.accounts.middleware.SessionIdleTimeoutMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',
    'axes.middleware.AxesMiddleware',  # Must be near the bottom of middleware stack
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.bookings.context_processors.cart_context',
            ],
            'autoescape': True,  # ⚠️ Never disable autoescaping
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
# Default to SQLite for local development; override with DATABASE_URL or prod.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Custom User Model (UUID pk + 7 roles)
AUTH_USER_MODEL = 'accounts.User'

# Password Hashing — Argon2 as the primary hasher
# WHY: Argon2 won the Password Hashing Competition (PHC) and is memory-hard,
# rendering GPU and ASIC brute-force attacks economically infeasible.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Authentication Backends (Axes must be at the top)
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Internationalization
LANGUAGE_CODE = 'th-th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================================================
# NON-NEGOTIABLE SECURITY SETTINGS (OWASP Compliant)
# ==============================================================================

# Session Cookie Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 43200           # 12 hours absolute maximum session lifetime
SESSION_SAVE_EVERY_REQUEST = True    # Updates session on every request for idle timeout
SESSION_IDLE_TIMEOUT = 1800          # 30 minutes idle timeout

# CSRF Security
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Browser Hardening Headers
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Axes (Brute-force protection)
AXES_ENABLED = config('AXES_ENABLED', default=True, cast=bool)
AXES_FAILURE_LIMIT = 5                 # 5 consecutive failed attempts
AXES_COOLOFF_TIME = 0.25               # 15 minutes lockout
AXES_RESET_ON_SUCCESS = True           # Reset counter on successful login
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'
AXES_LOCKOUT_URL = None
AXES_VERBOSE = True

# Content Security Policy (django-csp 4.0+)
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ("'self'",),
        'script-src': (
            "'self'",
            "'unsafe-inline'",  # Needed for dynamic script reactivity
            "'unsafe-eval'",    # Required for Alpine.js dynamic expression evaluation
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
            "https://cdn.tailwindcss.com",
        ),
        'style-src': (
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
            "https://unpkg.com",
            "https://cdn.tailwindcss.com",
        ),
        'font-src': (
            "'self'",
            "https://fonts.gstatic.com",
            "data:",
        ),
        'img-src': (
            "'self'",
            "data:",
            "https:",
        ),
        'connect-src': ("'self'",),
        'frame-ancestors': ("'none'",),
    }
}

# Rate Limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# ==============================================================================
# Hostinger SMTP & Centralized Notifications Suite
# ==============================================================================
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.hostinger.com')
EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='welltripth@welltripthailand.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='WellTrip Thailand <welltripth@welltripthailand.com>')
ADMIN_EMAIL = config('ADMIN_EMAIL', default='promlikit@sskru.ac.th')

