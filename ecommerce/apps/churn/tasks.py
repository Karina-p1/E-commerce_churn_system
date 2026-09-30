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


@shared_task(name='apps.churn.tasks.process_retention_order_task')
def process_retention_order_task(order_id):
    """
    Runs after an order becomes PAID.

    If the customer had an active win-back campaign when the order was
    created, record the return, coupon redemption, product purchase,
    recovered revenue, and re-score the customer's churn risk.
    """
    from apps.churn.retention import process_retention_order

    campaign = process_retention_order(order_id)

    if not campaign:
        return {
            'matched': False,
            'order_id': order_id,
        }

    return {
        'matched': True,
        'campaign_id': campaign.id,
        'order_id': order_id,
        'outcome': campaign.outcome,
        'used_campaign_coupon': campaign.used_campaign_coupon,
    }
