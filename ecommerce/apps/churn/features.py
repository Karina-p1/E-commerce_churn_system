from django.db import models as django_models

from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

from apps.activity.models import UserEvent, UserSession
from apps.orders.models import Order
from apps.products.models import Review
from apps.addresses.models import Address
from apps.complaints.models import Complaint

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

   # ── Hours Spent on App ───────────────────────────────

    # Average daily usage over the last 30 days.
    # If the account is newer than 30 days, use the account age instead.
    account_age_days = max((timezone.now() - user.date_joined).days, 1)

    lookback_days = min(account_age_days, 30)
    lookback_start = timezone.now() - timedelta(days=lookback_days)

    total_active_seconds = (
        UserSession.objects.filter(
            user=user,
            started_at__gte=lookback_start
        ).aggregate(
            total=Sum("active_seconds")
        )["total"] or 0
    )

    hours_on_app = round((total_active_seconds / 3600) / lookback_days, 2)

    # Real coupon usage: count of this user's non-cancelled orders that
    # had a coupon attached at checkout.
    coupon_used  = orders.filter(coupon__isnull=False).count()

    # ── Reward proxy ──────────────────────────────────
    # Real reward data: total coupon discount actually given to this
    # customer across their orders — this is genuine money returned
    # to them, not an invented percentage of spend. Much closer to
    # what "cashback" represents in the training data than a made-up
    # formula. Still capped at 300 — the training data's real
    # CashbackAmount maxed out around 325, so we avoid feeding the
    # model a number outside the range it was ever trained on.
    total_discount_given = sum(float(o.discount_amount or 0) for o in orders)
    cashback = round(min(total_discount_given, 300.0), 2)

    # ── Satisfaction score & complaints ───────────────
    reviews = Review.objects.filter(customer=user)

    if reviews.exists():
        avg_rating = reviews.aggregate(
            avg=django_models.Avg('rating')
        )['avg']
        satisfaction_score = round(avg_rating)
    else:
        satisfaction_score = 3

    # Real complaint data from the complaints app, not a review-rating
    # proxy. REJECTED complaints are excluded — those were reviewed by
    # an admin and deemed invalid, so they shouldn't count as a real
    # signal of a dissatisfied customer. PENDING / IN_PROGRESS / RESOLVED
    # all count, since even a resolved complaint means something went
    # wrong for this customer at some point.
    complain = 1 if Complaint.objects.filter(
        user=user
    ).exclude(status='REJECTED').exists() else 0

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