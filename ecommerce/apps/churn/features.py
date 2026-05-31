from django.utils import timezone
from apps.activity.models import UserEvent
from apps.orders.models import Order


def extract_features(user):
    # ── Orders ────────────────────────────────────────
    orders = Order.objects.filter(user=user).exclude(status='cancelled')
    order_count = orders.count()
    last_order  = orders.order_by('-created_at').first()

    days_since_last_order = 0
    if last_order:
        days_since_last_order = (timezone.now() - last_order.created_at).days

    # ── Tenure ────────────────────────────────────────
    tenure_months = max(1, (timezone.now() - user.date_joined).days // 30)

    # ── Activity events ───────────────────────────────
    logins = UserEvent.objects.filter(user=user, event_type='LOGIN').count()
    hours_on_app = round(logins * 0.5, 1)

    cart_adds = UserEvent.objects.filter(user=user, event_type='CART').count()
    coupon_used = 0  # add when you track coupons

    # ── Total spend ───────────────────────────────────
    total_spent = sum(
        float(o.total_price) for o in orders
    )
    avg_order_value = round(total_spent / order_count, 2) if order_count else 0
    cashback = round(total_spent * 0.02, 2)  # estimate 2% cashback

    return {
        'Tenure':                      tenure_months,
        'PreferredLoginDevice':        0,
        'CityTier':                    1,
        'WarehouseToHome':             15,
        'PreferredPaymentMode':        3,
        'Gender':                      1,
        'HourSpendOnApp':              hours_on_app,
        'NumberOfDeviceRegistered':    1,
        'PreferedOrderCat':            0,
        'SatisfactionScore':           3,
        'MaritalStatus':               2,
        'NumberOfAddress':             1,
        'Complain':                    0,
        'OrderAmountHikeFromlastYear': 15,
        'CouponUsed':                  coupon_used,
        'OrderCount':                  order_count,
        'DaySinceLastOrder':           days_since_last_order,
        'CashbackAmount':              cashback,
    }