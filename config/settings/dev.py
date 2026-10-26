"""
Development settings for local development.
"""
from .base import *

DEBUG = True

# In dev, allow localhost & local network if needed
ALLOWED_HOSTS = ['*']

# Simpler static storage for hot reloading
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Email backend (console in dev)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Optional: SQLite Database default or PostgreSQL if DATABASE_URL is set
import os
if os.environ.get('DATABASE_URL') and 'postgres' in os.environ.get('DATABASE_URL'):
    import psycopg
    # PostgreSQL configuration if specified
    pass
