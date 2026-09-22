from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from apps.notifications.models import Notification


@shared_task
def send_payment_reminder(order_id):
    from .models import Order

    try:
        order = Order.objects.select_related(
            'user').prefetch_related('items').get(id=order_id)
    except Order.DoesNotExist:
        return

    if order.payment_status != 'INITIATED':
        return

    user = order.user
    first_item = order.items.first()
    product_name = first_item.product_name if first_item else "your item(s)"
    extra_count = order.items.count() - 1
    item_line = product_name if extra_count <= 0 else f"{product_name} and {extra_count} more item(s)"

    checkout_url = getattr(settings, 'SITE_URL',
                           'http://localhost:8000') + reverse('checkout')

    subject = "You're one step away from completing your order"
    message = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        "We noticed you started an order but didn't finish checking out. "
        "Your item(s) are still saved for you:\n\n"
        f"{item_line} - Rs. {order.total_price}\n\n"
        f"Complete your purchase now: {checkout_url}\n\n"
        "If you ran into any issue during payment, just reply to this email "
        "and we'll help you sort it out.\n\n"
        "Thanks,\n"
        f"{getattr(settings, 'SITE_NAME', 'Our Store')}"
    )

    if user.email:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )

    Notification.objects.create(
        recipient=user,
        notif_type='PAYMENT_REMINDER',
        title="Complete your order",
        message=(
            f"You started an order for {item_line} (Rs. {order.total_price}) "
            f"but haven't completed payment yet. Complete checkout to secure your order."
        ),
    )
