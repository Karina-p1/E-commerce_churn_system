from django.db import models as django_models
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

from apps.activity.models import UserSession
from apps.orders.models import Order
from apps.products.models import Review
from apps.addresses.models import Address
from apps.complaints.models import Complaint


# The training notebook median-imputed missing DaySinceLastOrder with 3.0.
# A customer who has never ordered has no real "days since last order" value,
# so 3 is safer than 0, because 0 means "ordered today".
TRAINING_DAY_SINCE_LAST_ORDER_MEDIAN = 3


def _extract_features_and_metadata(user):
    """
    Build the exact 11 churn-model features plus UI-only explanation notes.

    The notes are NOT passed to the ML model.
    """

    # ── Orders ────────────────────────────────────────
    orders = Order.objects.filter(user=user).exclude(status='cancelled')
    order_count = orders.count()
    last_order = orders.order_by('-created_at').first()

    if last_order:
        days_since_last_order = max(
            0,
            (timezone.now() - last_order.created_at).days
        )
        no_order_fallback = False
    else:
        # Never ordered is not the same as ordered today.
        days_since_last_order = TRAINING_DAY_SINCE_LAST_ORDER_MEDIAN
        no_order_fallback = True

    # ── Tenure ────────────────────────────────────────
    account_age_days = max((timezone.now() - user.date_joined).days, 0)

    # Keep 0 months for genuinely brand-new accounts.
    tenure_months = max(0, account_age_days // 30)

    # ── Hours Spent on App ────────────────────────────
    # Average daily usage over at most the last 30 days.
    # Keep at least a 1-day denominator for accounts created today.
    usage_account_age_days = max(account_age_days, 1)
    lookback_days = min(usage_account_age_days, 30)
    lookback_start = timezone.now() - timedelta(days=lookback_days)

    total_active_seconds = (
        UserSession.objects.filter(
            user=user,
            started_at__gte=lookback_start
        ).aggregate(
            total=Sum("active_seconds")
        )["total"] or 0
    )

    hours_on_app = round(
        min((total_active_seconds / 3600) / lookback_days, 5.0),
        2
    )

    # ── Coupon usage ──────────────────────────────────
    coupon_used = orders.filter(coupon__isnull=False).count()

    # ── Cashback proxy ────────────────────────────────
    total_discount_given = sum(
        float(o.discount_amount or 0)
        for o in orders
    )
    cashback = round(min(total_discount_given, 300.0), 2)

    # ── Satisfaction score ────────────────────────────
    reviews = Review.objects.filter(customer=user)
    has_reviews = reviews.exists()

    if has_reviews:
        avg_rating = reviews.aggregate(
            avg=django_models.Avg('rating')
        )['avg']
        satisfaction_score = round(avg_rating)
    else:
        # Neutral fallback on the 1–5 scale.
        satisfaction_score = 3

    # ── Complaints ────────────────────────────────────
    complain = 1 if Complaint.objects.filter(
        user=user,
        status__in=['PENDING', 'IN_PROGRESS'],
    ).exists() else 0

    # ── Addresses ─────────────────────────────────────
    actual_address_count = Address.objects.filter(user=user).count()

    # Keep the model inside the range used during training.
    number_of_addresses = max(actual_address_count, 1)

    # ── Profile ───────────────────────────────────────
    gender = getattr(user, 'gender', None)
    marital_status = getattr(user, 'marital_status', None)

    missing_profile_fields = []

    if not gender:
        missing_profile_fields.append('gender')

    if not marital_status:
        missing_profile_fields.append('marital status')

    if missing_profile_fields:
        raise ValueError(
            "Cannot calculate churn score because this customer is missing "
            + " and ".join(missing_profile_fields)
            + ". Complete the profile first."
        )

    # ── Exact 11 model features ───────────────────────
    features = {
        'Gender': gender,
        'MaritalStatus': marital_status,
        'Tenure': tenure_months,
        'HourSpendOnApp': hours_on_app,
        'SatisfactionScore': satisfaction_score,
        'NumberOfAddress': number_of_addresses,
        'Complain': complain,
        'CouponUsed': coupon_used,
        'OrderCount': order_count,
        'DaySinceLastOrder': days_since_last_order,
        'CashbackAmount': cashback,
    }

    # ── UI-only explanation notes ─────────────────────
    input_notes = []

    # Always explain tenure conversion because days are converted to months.
    input_notes.append({
        'feature': 'Tenure',
        'actual': f'{account_age_days} day(s) old',
        'model_input': tenure_months,
        'message': (
            f'Account age is {account_age_days} day(s); '
            f'the model receives Tenure={tenure_months} month(s).'
        ),
    })

    if actual_address_count == 0:
        input_notes.append({
            'feature': 'NumberOfAddress',
            'actual': 0,
            'model_input': number_of_addresses,
            'message': (
                'Customer has 0 saved addresses; model receives 1 '
                'to stay compatible with the training-data range.'
            ),
        })

    if no_order_fallback:
        input_notes.append({
            'feature': 'DaySinceLastOrder',
            'actual': 'No previous order',
            'model_input': days_since_last_order,
            'message': (
                'Customer has never ordered; model receives '
                'DaySinceLastOrder=3 instead of 0, because 0 means ordered today.'
            ),
        })

    if not has_reviews:
        input_notes.append({
            'feature': 'SatisfactionScore',
            'actual': 'No reviews',
            'model_input': satisfaction_score,
            'message': (
                'Customer has no reviews; model receives neutral '
                'SatisfactionScore=3.'
            ),
        })

    return features, input_notes


def extract_features(user) -> dict:
    """
    Return only the exact 11 raw features expected by the churn model.

    Existing background scoring/service code should use this function.
    """
    features, _ = _extract_features_and_metadata(user)
    return features


def extract_features_with_metadata(user):
    """
    Return (features, input_notes) for the customer-detail page.

    input_notes explain model-compatible fallbacks without adding
    extra model features.
    """
    return _extract_features_and_metadata(user)
