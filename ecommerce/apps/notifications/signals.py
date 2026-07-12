from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.orders.models import Coupon
from .models import Notification
from .emails import send_bulk_html_email

User = get_user_model()


def _registered_users():
    return User.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )


def _describe_savings(coupon):
    if coupon.coupon_type == "BUY_X_GET_Y":
        savings = (
            "free"
            if coupon.get_discount_percent == 100
            else f"{coupon.get_discount_percent}% off"
        )
        return f"Buy {coupon.buy_quantity}, get {coupon.get_quantity} {savings}"

    if coupon.discount_type == "PERCENTAGE":
        return f"{coupon.discount_value}% off"

    return f"Rs. {coupon.discount_value} off"


@receiver(post_save, sender=Coupon)
def notify_users_of_new_coupon(sender, instance, created, **kwargs):
    if not created or not instance.is_active:
        return

    limited = instance.is_limited_time_offer

    title = (
        "New Limited-Time Offer!"
        if limited
        else "New Coupon Available!"
    )

    message = (
        f"Use coupon code {instance.code} and enjoy "
        f"{_describe_savings(instance)}."
    )

    if limited and instance.valid_until:
        message += (
            f" Valid until "
            f"{instance.valid_until:%d %b %Y %I:%M %p}."
        )

    users = list(_registered_users())

    Notification.objects.bulk_create([
        Notification(
            recipient=user,
            notif_type="COUPON",
            title=title,
            message=message,
            coupon=instance,
        )
        for user in users
    ])

    send_bulk_html_email(
        subject=title,
        template_name="notifications/emails/new_coupon_email.html",
        context={
            "coupon": instance,
            "title": title,
            "message": message,
            "site_url": settings.SITE_URL,
        },
        recipients=users,
    )