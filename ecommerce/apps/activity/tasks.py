from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import UserSession


SESSION_INACTIVITY_TIMEOUT_MINUTES = 30


@shared_task
def close_inactive_sessions():
    """
    Close analytics sessions that have been inactive
    for at least 30 minutes.
    """

    cutoff = timezone.now() - timedelta(
        minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES
    )

    sessions = UserSession.objects.filter(
        ended_at__isnull=True,
        last_activity__lte=cutoff,
    )

    updated = 0

    for session in sessions:
        # End at the last time we actually observed activity.
        session.ended_at = session.last_activity
        session.save(update_fields=["ended_at"])
        updated += 1

    return f"Closed {updated} inactive session(s)."