from django.db import models as django_models
from django.utils import timezone
from apps.activity.models import UserEvent
from apps.orders.models import Order
from apps.products.models import Review


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
    logins       = UserEvent.objects.filter(user=user, event_type='LOGIN').count()
    hours_on_app = round(logins * 0.5, 1)
    coupon_used  = 0

    # ── Spend ─────────────────────────────────────────
    total_spent = sum(float(o.total_price) for o in orders)
    cashback    = round(total_spent * 0.02, 2)

    # ── Preferred payment mode ─────────────────────────
    last_paid_order = (
        orders
        .filter(payment_status='PAID')
        .order_by('-paid_at')
        .first()
    )

    preferred_payment = 'E wallet'
    if last_paid_order:
        payment_map = {
            'ESEWA':  'E wallet',
            'KHALTI': 'E wallet',
            'CREDIT': 'Credit Card',
            'DEBIT':  'Debit Card',
            'COD':    'COD',
        }
        preferred_payment = payment_map.get(
            last_paid_order.payment_method.upper(),
            'E wallet'
        )

    # ── Satisfaction score & complaints ───────────────
    reviews = Review.objects.filter(customer=user)

    if reviews.exists():
        avg_rating = reviews.aggregate(
            avg=django_models.Avg('rating')
        )['avg']
        satisfaction_score = round(avg_rating)   # 1–5
    else:
        satisfaction_score = 3                   # neutral default

    complain = 1 if reviews.filter(rating__lte=2).exists() else 0

    return {
        # ── Raw text for categoricals — predictor.py encodes these ──
        'PreferredLoginDevice':        'Mobile Phone',  # TODO: track via middleware
        'PreferredPaymentMode':        preferred_payment,
        'Gender':                      'Male',          # TODO: user profile
        'PreferedOrderCat':            'Mobile Phone',  # TODO: track from orders
        'MaritalStatus':               'Single',        # TODO: user profile

        # ── Numeric fields ───────────────────────────────────────────
        'Tenure':                      tenure_months,
        'CityTier':                    1,
        'WarehouseToHome':             15,
        'HourSpendOnApp':              hours_on_app,
        'NumberOfDeviceRegistered':    1,
        'SatisfactionScore':           satisfaction_score,
        'NumberOfAddress':             1,
        'Complain':                    complain,
        'OrderAmountHikeFromlastYear': 15,
        'CouponUsed':                  coupon_used,
        'OrderCount':                  order_count,
        'DaySinceLastOrder':           days_since_last_order,
        'CashbackAmount':              cashback,
    }