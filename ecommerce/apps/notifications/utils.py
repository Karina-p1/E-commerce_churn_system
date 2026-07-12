from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import Notification

User = get_user_model()


def notify_all_users(
    *,
    title,
    message,
    coupon=None,
    notif_type="GENERAL",
    email_subject=None,
    email_template=None,
    context=None,
):
    """
    Creates in-app notifications and sends email
    to every registered user.
    """

    users = User.objects.filter(
        is_active=True,
        is_staff=False
    )

    context = context or {}

    for user in users:

        # --------------------------
        # In-App Notification
        # --------------------------
        Notification.objects.create(
            recipient=user,
            notif_type=notif_type,
            title=title,
            message=message,
            coupon=coupon,
        )

        # --------------------------
        # Email
        # --------------------------
        if user.email and email_template:

            html_message = render_to_string(
                email_template,
                {
                    **context,
                    "user": user,
                    "coupon": coupon,
                    "site_url": settings.SITE_URL,
                }
            )

            send_mail(
                subject=email_subject or title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=True,
            )