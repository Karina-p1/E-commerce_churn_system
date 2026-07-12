from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import UserEvent
from .models import UserSession
from django.utils import timezone

@receiver(user_logged_in)
def login_log(sender, request, user, **kwargs):
    UserEvent.objects.create(
        user=user,
        event_type='LOGIN'
    )
    UserSession.objects.create(
        user=user
    )


@receiver(user_logged_out)
def logout_log(sender, request, user, **kwargs):
    UserEvent.objects.create(
        user=user,
        event_type='LOGOUT'
    )
    UserSession.objects.filter(
        user=user,
        ended_at__isnull=True
    ).update(
        ended_at=timezone.now()
    )