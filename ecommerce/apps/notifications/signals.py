from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from apps.orders.models import Coupon
from .models import Notification

User = get_user_model()


def _registered_users():
    return User.objects.filter(is_active=True, is_staff=False, is_superuser=False)


def _describe_savings(coupon):
    if coupon.coupon_type == 'BUY_X_GET_Y':
        get_pct = coupon.get_discount_percent
        savings = "free" if get_pct == 100 else f"{get_pct}% off"
        return f"Buy {coupon.buy_quantity}, get {coupon.get_quantity} {savings}"

    if coupon.discount_type == 'PERCENTAGE':
        return f"{coupon.discount_value}% off"

    return f"Rs.{coupon.discount_value} off"


def _send_new_coupon_email(coupon, recipients, title, message):
    """
    One email, BCC'd to every recipient with a valid email address, so no
    customer sees anyone else's address. Sent synchronously — fine for a
    small user base; if this ever grows large, move this to a background
    task (e.g. Celery) so admin's save request doesn't wait on SMTP.
    """
    recipient_emails = [u.email for u in recipients if u.email]

    if not recipient_emails:
        return

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@example.com'

    text_body = (
        f"{message}\n\n"
        f"Log in to your account to use this offer before it's gone.\n"
    )
    html_body = f"""
        <p>{message}</p>
        <p><a href="{getattr(settings, 'SITE_URL', '')}">Visit the store</a> to use this offer.</p>
    """

    email = EmailMultiAlternatives(
        subject=title,
        body=text_body,
        from_email=from_email,
        to=[from_email],       # nominal "to" — actual recipients are BCC'd below
        bcc=recipient_emails,
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)  # fail loudly so admin knows if email sending is broken


@receiver(post_save, sender=Coupon)
def notify_users_of_new_coupon(sender, instance, created, **kwargs):
    # Only fire once, when the coupon is first created and already active.
    if not created or not instance.is_active:
        return

    is_limited_time = instance.is_limited_time_offer
    title = "New limited-time offer!" if is_limited_time else "New coupon available!"

    message = f"Use code {instance.code} \u2014 {_describe_savings(instance)}"
    if is_limited_time:
        message += f". Valid until {instance.valid_until:%b %d, %Y}."

    recipients = list(_registered_users())

    Notification.objects.bulk_create([
        Notification(
            recipient=user,
            notif_type='COUPON',
            title=title,
            message=message,
            coupon=instance,
        )
        for user in recipients
    ])

    _send_new_coupon_email(instance, recipients, title, message)