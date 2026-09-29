from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import UserEvent
from .models import UserSession
from django.utils import timezone

@receiver(user_logged_in)
def login_log(sender, request, user, **kwargs):

    UserEvent.objects.create(
        user=user,
        event_type="LOGIN"
    )

    UserSession.objects.filter(
        user=user,
        ended_at__isnull=True
    ).update(
        ended_at=timezone.now()
    )

    UserSession.objects.create(
        user=user,
        last_activity=timezone.now(),
    )


@receiver(user_logged_out)
def close_session(sender, request, user, **kwargs):
    # Keep logout itself safe even if Django supplies user=None.
    if user is None:
        return

    UserEvent.objects.create(
        user=user,
        event_type="LOGOUT"
    )

    session = (
        UserSession.objects.filter(
            user=user,
            ended_at__isnull=True
        )
        .order_by("-started_at")
        .first()
    )

    if session:
        session.close()
