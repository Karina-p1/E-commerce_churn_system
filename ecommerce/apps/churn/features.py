from django.utils import timezone
from apps.activity.models import UserEvent
from apps.orders.models import Order


def extract_features(user) -> dict:
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
    logins      = UserEvent.objects.filter(user=user, event_type='LOGIN').count()
    hours_on_app = round(logins * 0.5, 1)
    coupon_used  = 0

    # ── Spend ─────────────────────────────────────────
    total_spent = sum(float(o.total_price) for o in orders)
    cashback    = round(total_spent * 0.02, 2)

    # ── Satisfaction / complaints ──────────────────────
    # If you track complaints or ratings, pull them here.
    # Using sensible defaults until you wire those models up.
    satisfaction_score = 3
    complain           = 0

    return {
        # ── Raw text for categoricals — predictor.py encodes these ──
        'PreferredLoginDevice':          'Mobile Phone',  # update when you track this
        'PreferredPaymentMode':          'Debit Card',    # update when you track this
        'Gender':                        'Male',          # update from user profile
        'PreferedOrderCat':              'Mobile Phone',  # update when you track this
        'MaritalStatus':                 'Single',        # update from user profile

        # ── Numeric fields — pass as numbers directly ────────────────
        'Tenure':                        tenure_months,
        'CityTier':                      1,
        'WarehouseToHome':               15,
        'HourSpendOnApp':                hours_on_app,
        'NumberOfDeviceRegistered':      1,
        'SatisfactionScore':             satisfaction_score,
        'NumberOfAddress':               1,
        'Complain':                      complain,
        'OrderAmountHikeFromlastYear':   15,
        'CouponUsed':                    coupon_used,
        'OrderCount':                    order_count,
        'DaySinceLastOrder':             days_since_last_order,
        'CashbackAmount':                cashback,
    }