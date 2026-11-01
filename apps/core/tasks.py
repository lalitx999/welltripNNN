"""
Email tasks. SMTP can take seconds or hang, so views enqueue these instead of
sending inline. Tasks take IDs, not model instances, and reload fresh rows.
"""
import smtplib

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.core.services import notifications


@shared_task(
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(subject, message, recipient):
    """The only place that talks to SMTP. Retries ~5 times over ~15 minutes."""
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)


def _load_payment(payment_id):
    from apps.payments.models import Payment

    return (
        Payment.objects.select_related("booking__customer")
        .filter(pk=payment_id)
        .first()
    )


@shared_task
def send_booking_voucher_task(payment_id):
    payment = _load_payment(payment_id)
    if payment:
        notifications.send_booking_voucher_and_order_alert(payment)


@shared_task
def send_slip_rejected_task(payment_id, reason):
    payment = _load_payment(payment_id)
    if payment:
        notifications.send_slip_rejected_alert(payment, reason)


@shared_task
def send_merchant_kyc_decision_task(user_id, is_approved, reason=""):
    from apps.accounts.models import User

    merchant = User.objects.filter(pk=user_id).first()
    if merchant:
        notifications.send_merchant_kyc_decision(merchant, is_approved=is_approved, reason=reason)
