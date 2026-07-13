from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import UserSession


@shared_task
def close_inactive_sessions():

    cutoff = timezone.now() - timedelta(minutes=5)

    sessions = UserSession.objects.filter(
        ended_at__isnull=True,
        last_activity__lt=cutoff
    )

    for session in sessions:
        session.ended_at = session.last_activity
        session.save(update_fields=["ended_at"])