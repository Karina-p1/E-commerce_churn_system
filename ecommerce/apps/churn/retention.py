import random
import string
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.orders.models import Coupon
from apps.notifications.models import Notification


def _generate_coupon_code(user):
    """A short, unique code for this specific win-back offer."""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"WEMISSYOU-{user.id}-{suffix}"


def trigger_winback(user):
    """
    Called once, the moment a customer's risk_level newly flips from
    'low' (or no prior score at all) to 'high'. Creates a real,
    redeemable coupon and notifies the customer — turning a churn
    SCORE into an actual retention ACTION instead of a number that
    just sits on a dashboard.

    Note on scope: Coupon has no per-user restriction field in the
    database, so this isn't cryptographically locked to one person —
    it's a unique, single-use code (max_uses=1) that's only ever
    shown to this one customer, via their notification (and email).
    Good enough for a win-back nudge; a stranger who somehow saw the
    code could technically redeem it once instead of the customer.

    Returns the created Coupon, or None if something went wrong
    (never raises — a failed win-back attempt should never break the
    scoring run itself).
    """
    try:
        coupon = Coupon.objects.create(
            code=_generate_coupon_code(user),
            coupon_type='STANDARD',
            discount_type='PERCENTAGE',
            discount_value=10,
            min_order_amount=0,
            max_uses=1,
            is_active=True,
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
        )

        Notification.objects.create(
            recipient=user,
            notif_type='COUPON',
            title="We miss you! Here's 10% off",
            message=(
                f"Use code {coupon.code} for 10% off your next order. "
                f"Valid for 7 days."
            ),
            coupon=coupon,
        )

        # Email is best-effort — a failed send should never break scoring.
        if getattr(settings, 'EMAIL_HOST_USER', None) and user.email:
            try:
                send_mail(
                    subject="We miss you at ShopMart \U0001F6CD\uFE0F",
                    message=(
                        f"Hi {user.username},\n\n"
                        f"It's been a while since your last order! Here's "
                        f"{coupon.discount_value}% off your next purchase — "
                        f"use code {coupon.code}, valid for the next 7 days.\n\n"
                        f"\u2014 ShopMart"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass

        return coupon

    except Exception:
        # Never let a retention-action failure break the scoring run.
        return None