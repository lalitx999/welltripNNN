"""
Celery app for background work (slip OCR, emails, AI calls).
Tasks use DjangoTask so views can call `.delay_on_commit()` and the worker
never reads rows the request has not committed yet.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("welltrip", task_cls="celery.contrib.django.task:DjangoTask")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
