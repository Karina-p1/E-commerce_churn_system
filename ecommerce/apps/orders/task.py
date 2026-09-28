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


STATUS_LABELS = {
    "pending": "Pending",
    "processing": "Processing",
    "shipped": "Shipped",
    "delivered": "Delivered",
}

# Short title for the notification
STATUS_TITLES = {
    "processing": "Your order is being prepared",
    "shipped": "Your order has been shipped",
    "delivered": "Your order has been delivered",
}

# Main sentence, {item} is replaced with the product name
STATUS_MESSAGES = {
    "processing": "Good news! We have started processing {item} for you.",
    "shipped": "{item} is on its way to you. It will reach you soon.",
    "delivered": "{item} has been delivered. We hope you enjoy it!",
}


@shared_task
def send_order_status_update(order_id, old_status, new_status):
    from apps.orders.models import Order
    from apps.notifications.models import Notification

    order = (
        Order.objects
        .select_related("user")
        .prefetch_related("items")
        .filter(pk=order_id)
        .first()
    )
    if not order:
        return

    # Product name(s) instead of the order number
    first_item = order.items.first()
    product_name = first_item.product_name if first_item else "your order"
    extra_count = order.items.count() - 1
    item_line = (
        product_name
        if extra_count <= 0
        else f"{product_name} and {extra_count} more item(s)"
    )

    old_label = STATUS_LABELS.get(old_status, old_status)
    new_label = STATUS_LABELS.get(new_status, new_status)

    title = STATUS_TITLES.get(new_status, f"Order {new_label}")
    main_line = STATUS_MESSAGES.get(
        new_status, "The status of {item} is now " + new_label + "."
    ).format(item=item_line)

    message = main_line 

    # 1. In-app notification
    Notification.objects.create(
        recipient=order.user,
        notif_type="ORDER_STATUS",
        title=title,
        message=message,
    )

    # 2. Email (a mail problem must not break the notification above)
    if order.user.email:
        try:
            send_mail(
                subject=f"{title}: {product_name}",
                message=(
                    f"Hi {order.user.get_full_name() or order.user.username},\n\n"
                    f"{main_line}\n\n"
                    f"Thanks for shopping with "
                    f"{getattr(settings, 'SITE_NAME', 'us')}."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[order.user.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Order status email failed for order {order.id}: {e}")