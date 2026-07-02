from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Order
from apps.analytics.tasks import paid_order_created


@receiver(post_save, sender=Order)
def order_created(sender, instance, created, **kwargs):
    """
    Runs automatically whenever a new Order is created.
    """

    if not created:
        return

    print(f"New Order Created: #{instance.id}")

    # Only update revenue if the order is already paid
    if instance.payment_status == "PAID":
        transaction.on_commit(
            lambda: paid_order_created.delay(instance.id)
        )