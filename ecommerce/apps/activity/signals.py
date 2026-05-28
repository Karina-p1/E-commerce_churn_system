from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out
)
from django.db.models.signals import post_save
from django.dispatch import receiver

# from apps.orders.models import Order
from .models import UserEvent
from django.dispatch import receiver

@receiver(user_logged_in)
def login_log(sender,request,user,**kwargs):

    UserEvent.objects.create(
        user=user,
        event_type='LOGIN'
    )


@receiver(user_logged_out)
def logout_log(sender,request,user,**kwargs):

    UserEvent.objects.create(
        user=user,
        event_type='LOGOUT'
    )

# @receiver(post_save,sender=Order)
# def order_log(
#     sender,
#     instance,
#     created,
#     **kwargs
# ):

#     if created:

#         UserEvent.objects.create(
#             user=instance.user,
#             event_type='ORDER'
#         )