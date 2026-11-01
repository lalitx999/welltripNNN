from celery import shared_task

from .services import complete_recommendation


@shared_task
def run_recommendation_task(log_id):
    """DeepSeek can take ~12s; the assessment page polls the log for the result."""
    complete_recommendation(log_id)
