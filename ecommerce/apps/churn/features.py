from django.db import models as django_models
from django.utils import timezone
from apps.activity.models import UserEvent
from apps.orders.models import Order
from apps.products.models import Review
from apps.addresses.models import Address


def extract_features(user) -> dict:
    """
    Extracts the 11 raw features kept for the churn model
    (per the updated requirements — dropped PreferredLoginDevice,
    CityTier, WarehouseToHome, PreferredPaymentMode, PreferedOrderCat,
    OrderAmountHikeFromlastYear, NumberOfDeviceRegistered).
    """

    # ── Orders ────────────────────────────────────────
    orders      = Order.objects.filter(user=user).exclude(status='cancelled')
    order_count = orders.count()
    last_order  = orders.order_by('-created_at').first()

    days_since_last_order = 0
    if last_order:
        days_since_last_order = (timezone.now() - last_order.created_at).days

    # ── Tenure ────────────────────────────────────────
    tenure_months = max(1, (timezone.now() - user.date_joined).days // 30)

    # ── Activity ──────────────────────────────────────
    # NOTE: training data's HourSpendOnApp was a self-reported daily
    # average bounded 0-5. We don't track real session duration yet,
    # so this is a synthetic proxy based on DISTINCT ACTIVE DAYS in the
    # last 30 (or since account creation, if younger than 30 days) —
    # this avoids unfairly penalizing brand-new accounts that simply
    # haven't existed long enough to rack up 30 days of activity.
    account_age_days = max((timezone.now() - user.date_joined).days, 1)
    lookback_days = min(account_age_days, 30)
    lookback_start = timezone.now() - timezone.timedelta(days=lookback_days)

    active_days = (
        UserEvent.objects
        .filter(user=user, event_type='LOGIN', created_at__gte=lookback_start)
        .annotate(day=django_models.functions.TruncDate('created_at'))
        .values('day')
        .distinct()
        .count()
    )
    hours_on_app = round(min(active_days / lookback_days * 5, 5.0), 1)

    # Real coupon usage: count of this user's non-cancelled orders that
    # had a coupon attached at checkout.
    coupon_used  = orders.filter(coupon__isnull=False).count()

    # ── Spend ─────────────────────────────────────────
    # NOTE: training data's CashbackAmount was a real monthly reward
    # amount bounded 0-324.99 (mean ~177). We don't track real cashback
    # yet, so this is a synthetic proxy from total spend — capped at
    # 300 to stay in-range. High spenders will all cap out at 300,
    # which loses some granularity, but keeps predictions reliable
    # rather than extrapolating wildly beyond the trained distribution.
    total_spent = sum(float(o.total_price) for o in orders)
    cashback    = round(min(total_spent * 0.02, 300.0), 2)

    # ── Satisfaction score & complaints ───────────────
    reviews = Review.objects.filter(customer=user)

    if reviews.exists():
        avg_rating = reviews.aggregate(
            avg=django_models.Avg('rating')
        )['avg']
        satisfaction_score = round(avg_rating)
    else:
        satisfaction_score = 3

    complain = 1 if reviews.filter(rating__lte=2).exists() else 0

    # ── Addresses ─────────────────────────────────────
    number_of_addresses = Address.objects.filter(user=user).count()
    if number_of_addresses == 0:
        number_of_addresses = 1  # fallback — model was trained on min=1 in source data

    # ── Profile ───────────────────────────────────────
    gender         = user.gender or 'Male'
    marital_status = user.marital_status or 'Single'

    return {
        # ── Categoricals — predictor.py encodes these via encoding_maps.pkl ──
        'Gender':                gender,
        'MaritalStatus':         marital_status,

        # ── Numerics — the 9 kept numeric features ──────────────────────────
        'Tenure':                tenure_months,
        'HourSpendOnApp':        hours_on_app,
        'SatisfactionScore':     satisfaction_score,
        'NumberOfAddress':       number_of_addresses,
        'Complain':              complain,
        'CouponUsed':            coupon_used,
        'OrderCount':            order_count,
        'DaySinceLastOrder':     days_since_last_order,
        'CashbackAmount':        cashback,
    }