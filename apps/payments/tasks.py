from celery import shared_task

from apps.payments.services import SlipPendingError, verify_slip_automatically


@shared_task(bind=True, max_retries=3)
def verify_slip_task(self, slip_id):
    """EasySlip can take up to 20s, so it never runs inside the upload request."""
    try:
        verify_slip_automatically(slip_id)
    except SlipPendingError as exc:
        # Some banks (e.g. Bangkok Bank) publish a slip only ~5 minutes after the transfer
        if self.request.retries >= self.max_retries:
            from apps.payments.models import PaymentSlip
            PaymentSlip.objects.filter(pk=slip_id, verification_notes="").update(
                verification_notes="ธนาคารยังไม่ยืนยันสลิปหลังลองซ้ำหลายครั้ง (ส่งต่อให้แอดมินตรวจ)"
            )
            return
        raise self.retry(exc=exc, countdown=180)
