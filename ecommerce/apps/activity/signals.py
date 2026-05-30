from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import UserEvent


@receiver(user_logged_in)
def login_log(sender, request, user, **kwargs):
    UserEvent.objects.create(
        user=user,
        event_type='LOGIN'
    )


@receiver(user_logged_out)
def logout_log(sender, request, user, **kwargs):
    UserEvent.objects.create(
        user=user,
        event_type='LOGOUT'
    )