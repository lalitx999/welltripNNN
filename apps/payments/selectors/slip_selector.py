from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.payments.models import PaymentSlip, SlipVerificationStatus

# Auto-check normally finishes in seconds; stop polling after this and fall back to "waiting for staff"
SLIP_POLL_WINDOW = timedelta(minutes=3)


def latest_slip_for_booking(booking):
    """Newest slip the customer uploaded for this booking, or None."""
    return (
        PaymentSlip.objects.filter(payment__booking=booking)
        .only("id", "verification_status", "verification_notes", "uploaded_at")
        .order_by("-uploaded_at")
        .first()
    )


def slip_status_context(booking):
    """Context for payments/partials/slip_status.html."""
    slip = latest_slip_for_booking(booking)
    polling = bool(
        slip
        and settings.EASYSLIP_API_KEY
        and slip.verification_status == SlipVerificationStatus.PENDING_CHECK
        and timezone.now() - slip.uploaded_at < SLIP_POLL_WINDOW
    )
    return {"booking": booking, "slip": slip, "polling": polling}
