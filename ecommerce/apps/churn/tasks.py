import logging

from celery import shared_task

from apps.churn.services import score_all_customers

logger = logging.getLogger(__name__)


@shared_task(name='apps.churn.tasks.score_all_customers_task')
def score_all_customers_task():
    """
    Celery Beat task — re-scores every customer for churn risk.

    Runs automatically every 24 hours (see CELERY_BEAT_SCHEDULE in
    settings.py). Uses the same score_all_customers() logic as the
    manual `python manage.py score_customers` command, so scheduled
    and on-demand scoring always behave identically.

    Progress is written to the Celery worker's log instead of stdout,
    since there's no terminal to print to in a background task.
    """
    logger.info("Starting scheduled churn scoring run...")
    summary = score_all_customers(debug=False, log=logger.info)
    logger.info(f"Scheduled churn scoring finished: {summary}")
    return summary