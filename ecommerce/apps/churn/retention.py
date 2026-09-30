import logging
import random
import string
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification
from apps.orders.models import Coupon, Order

from .models import RetentionCampaign


logger = logging.getLogger(__name__)

# Do not repeatedly send win-back offers to a customer whose score
# bounces across the threshold.
WINBACK_COOLDOWN_DAYS = 30

# A campaign has seven days to generate a return order.
WINBACK_VALID_DAYS = 7


def _generate_coupon_code(user):
    """Generate a short unique code for this customer's win-back offer."""
    suffix = ''.join(
        random.choices(string.ascii_uppercase + string.digits, k=5)
    )
    return f"WEMISSYOU-{user.id}-{suffix}"


def trigger_winback(user, source_score=None):
    """
    Called when a customer newly crosses into high churn risk.

    Creates:
      1. a private single-customer coupon,
      2. an in-app notification,
      3. a RetentionCampaign record containing the BEFORE churn score.

    Returns the created Coupon, or None if the customer is on cooldown
    or the retention action fails.

    Retention failures never break churn scoring.
    """
    try:
        cutoff = timezone.now() - timedelta(days=WINBACK_COOLDOWN_DAYS)

        # Use the campaign table as the source of truth once it exists.
        if RetentionCampaign.objects.filter(
            customer=user,
            sent_at__gte=cutoff,
        ).exists():
            return None

        # Backward compatibility for old WEMISSYOU coupons created before
        # RetentionCampaign existed.
        if Coupon.objects.filter(
            assigned_user=user,
            code__startswith=f"WEMISSYOU-{user.id}-",
            created_at__gte=cutoff,
        ).exists():
            return None

        if source_score is None:
            source_score = (
                user.churn_scores
                .order_by('-predicted_at')
                .first()
            )

        if source_score is None:
            logger.warning(
                "Win-back skipped for user %s because no saved churn score exists.",
                user.pk,
            )
            return None

        now = timezone.now()
        expires_at = now + timedelta(days=WINBACK_VALID_DAYS)

        with transaction.atomic():
            coupon = Coupon.objects.create(
                code=_generate_coupon_code(user),
                coupon_type='STANDARD',
                discount_type='PERCENTAGE',
                discount_value=10,
                min_order_amount=0,
                max_uses=1,
                is_active=True,
                assigned_user=user,
                is_public=False,
                valid_from=now,
                valid_until=expires_at,
            )

            notification = Notification.objects.create(
                recipient=user,
                notif_type='COUPON',
                title="We miss you! Here's 10% off",
                message=(
                    f"Use code {coupon.code} for 10% off your next order. "
                    f"Valid for {WINBACK_VALID_DAYS} days."
                ),
                coupon=coupon,
            )

            RetentionCampaign.objects.create(
                customer=user,
                source_score=source_score,
                coupon=coupon,
                notification=notification,
                before_score=source_score.score,
                before_risk_level=source_score.risk_level,
                status='SENT',
                outcome='PENDING',
                expires_at=expires_at,
            )

        # Email is deliberately best-effort. SMTP trouble must never make
        # the churn scoring run fail.
        if getattr(settings, 'EMAIL_HOST_USER', None) and user.email:
            try:
                send_mail(
                    subject="We miss you at ShopMart 🛍️",
                    message=(
                        f"Hi {user.username},\n\n"
                        f"Here's {coupon.discount_value}% off your next purchase. "
                        f"Use code {coupon.code}, valid for the next "
                        f"{WINBACK_VALID_DAYS} days.\n\n"
                        "— ShopMart"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                logger.exception(
                    "Win-back email failed for user %s.",
                    user.pk,
                )

        return coupon

    except Exception:
        logger.exception(
            "Win-back campaign creation failed for user %s.",
            getattr(user, 'pk', None),
        )
        return None


def mark_campaign_viewed(notification):
    """Record that the customer opened/read one retention notification."""
    campaign = (
        RetentionCampaign.objects
        .filter(notification=notification)
        .first()
    )

    if not campaign:
        return None

    changed_fields = []

    if campaign.viewed_at is None:
        campaign.viewed_at = timezone.now()
        changed_fields.append('viewed_at')

    if campaign.status == 'SENT':
        campaign.status = 'VIEWED'
        changed_fields.append('status')

    if changed_fields:
        campaign.save(update_fields=changed_fields)

    return campaign


def mark_campaigns_viewed(notification_ids):
    """
    Bulk equivalent used by the notification centre's "Mark all read".
    """
    if not notification_ids:
        return 0

    now = timezone.now()
    campaigns = RetentionCampaign.objects.filter(
        notification_id__in=notification_ids,
        viewed_at__isnull=True,
    )

    updated = 0
    for campaign in campaigns:
        campaign.viewed_at = now
        if campaign.status == 'SENT':
            campaign.status = 'VIEWED'
            campaign.save(update_fields=['viewed_at', 'status'])
        else:
            campaign.save(update_fields=['viewed_at'])
        updated += 1

    return updated


def process_retention_order(order_id):
    """
    Close the retention loop after an order becomes PAID.

    Important:
    We NEVER manually subtract from the churn score.

    The customer's real behaviour changes first (new order, coupon use,
    days-since-last-order, cashback proxy, etc.), then the real churn model
    is run again. We compare that genuine AFTER score with the BEFORE score.
    """
    order = (
        Order.objects
        .select_related('user', 'coupon')
        .prefetch_related('items')
        .filter(pk=order_id, payment_status='PAID')
        .first()
    )

    if not order:
        return None

    # Idempotency: Celery retry / duplicate callback must not re-score or
    # double-count the same recovered order.
    existing = (
        RetentionCampaign.objects
        .filter(recovered_order=order)
        .first()
    )
    if existing:
        return existing

    # Attribute a paid order to the most recent active campaign only when
    # the ORDER ITSELF was created during the campaign window.
    # This also handles COD: the order can be placed during the 7-day offer
    # and become paid later when delivered.
    campaign = (
        RetentionCampaign.objects
        .select_related('customer', 'coupon')
        .filter(
            customer=order.user,
            sent_at__lte=order.created_at,
            expires_at__gte=order.created_at,
            recovered_order__isnull=True,
        )
        .order_by('-sent_at')
        .first()
    )

    if not campaign:
        return None

    used_campaign_coupon = (
        campaign.coupon_id is not None
        and order.coupon_id == campaign.coupon_id
    )

    returned_at = order.paid_at or timezone.now()

    campaign.returned_at = returned_at
    campaign.recovered_order = order
    campaign.recovered_revenue = Decimal(order.total_price or 0)
    campaign.used_campaign_coupon = used_campaign_coupon
    campaign.status = 'RECOVERED'

    if used_campaign_coupon:
        campaign.redeemed_at = returned_at

    campaign.save(update_fields=[
        'returned_at',
        'recovered_order',
        'recovered_revenue',
        'used_campaign_coupon',
        'status',
        'redeemed_at',
    ])

    # Local import prevents:
    # services.py -> retention.py -> services.py
    from .services import score_customer

    try:
        # A post-campaign measurement should never create another campaign.
        scoring = score_customer(
            order.user,
            debug=False,
            log=None,
            allow_winback=False,
        )

        result = scoring['result']

        campaign.after_score = result['score']
        campaign.after_risk_level = result['risk_level']
        campaign.score_change = round(
            campaign.after_score - campaign.before_score,
            3,
        )
        campaign.rescored_at = timezone.now()

        if campaign.after_risk_level == 'low':
            campaign.outcome = 'RISK_REDUCED'
        elif campaign.after_score < campaign.before_score:
            campaign.outcome = 'IMPROVED_STILL_HIGH'
        else:
            campaign.outcome = 'RETURNED_NO_IMPROVEMENT'

        campaign.save(update_fields=[
            'after_score',
            'after_risk_level',
            'score_change',
            'rescored_at',
            'outcome',
        ])

    except Exception:
        # The paid return is still real even if re-scoring fails.
        logger.exception(
            "Post-retention re-score failed for campaign %s / order %s.",
            campaign.pk,
            order.pk,
        )

    return campaign


def expire_retention_campaigns():
    """
    Mark unanswered campaigns expired once their response window closes.

    A campaign with a recovered order is never expired.
    """
    now = timezone.now()

    campaigns = (
        RetentionCampaign.objects
        .filter(
            expires_at__lt=now,
            recovered_order__isnull=True,
        )
        .exclude(status='EXPIRED')
    )

    return campaigns.update(
        status='EXPIRED',
        outcome='EXPIRED',
    )
