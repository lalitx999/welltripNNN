from celery import shared_task

from apps.bookings.services.checkout import cancel_and_restore_expired_bookings


@shared_task
def expire_unpaid_bookings_task():
    """Runs every minute (celery beat): frees stock held by checkouts nobody paid for."""
    return cancel_and_restore_expired_bookings()
