from celery import shared_task

from apps.payments.services import verify_slip_automatically


@shared_task
def verify_slip_task(slip_id):
    """EasySlip OCR can take up to 20s, so it never runs inside the upload request."""
    verify_slip_automatically(slip_id)
