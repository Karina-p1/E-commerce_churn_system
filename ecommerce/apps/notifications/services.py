from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

from .models import Notification

User = get_user_model()


def send_coupon_notifications(coupon):
    """
    Send both:
    - In-app notifications
    - Email notifications
    to every active registered user.
    """

    users = User.objects.filter(
        is_active=True,
        is_staff=False
    )

    subject = f"🎉 New Coupon: {coupon.code}"

    if coupon.coupon_type == "FIRST_ORDER":
        title = "First Order Coupon"
        message = (
            f"Use coupon {coupon.code} on your first order "
            f"and save!"
        )

    elif coupon.coupon_type == "BUY_X_GET_Y":
        title = "Buy X Get Y Offer"
        message = (
            f"Buy {coupon.buy_quantity} Get "
            f"{coupon.get_quantity} using coupon {coupon.code}."
        )

    elif coupon.coupon_type == "MIN_QUANTITY":
        title = "Bulk Purchase Coupon"
        message = (
            f"Buy at least {coupon.min_quantity} items "
            f"to use coupon {coupon.code}."
        )

    else:
        title = "New Coupon Available"
        message = (
            f"Use coupon {coupon.code} "
            f"and enjoy amazing savings."
        )

    # ----------------------------
    # In-app notifications
    # ----------------------------

    notifications = [
        Notification(
            recipient=user,
            notif_type="COUPON",
            title=title,
            message=message,
            coupon=coupon,
        )
        for user in users
    ]

    Notification.objects.bulk_create(notifications)

    # ----------------------------
    # Email notifications
    # ----------------------------

    recipient_list = [
        u.email
        for u in users
        if u.email
    ]

    if recipient_list:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True,
        )
def send_offer_expiring_notifications(coupon):

    if not coupon.valid_until:
        return

    users = User.objects.filter(
        is_active=True,
        is_staff=False
    )

    title = "Limited Time Offer"

    message = (
        f"Hurry! Coupon {coupon.code} expires on "
        f"{coupon.valid_until.strftime('%d %b %Y %I:%M %p')}."
    )

    Notification.objects.bulk_create([
        Notification(
            recipient=user,
            notif_type="OFFER_EXPIRING",
            title=title,
            message=message,
            coupon=coupon,
        )
        for user in users
    ])

    recipient_list = [
        u.email
        for u in users
        if u.email
    ]

    if recipient_list:
        send_mail(
            "⏰ Offer Expiring Soon",
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=True,
        )
    