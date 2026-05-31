from django.utils import timezone as dj_timezone
from apps.activity.models import UserEvent


def extract_features(user):
    """
    Feature dict matched EXACTLY to trained model columns (order matters).
    0: Tenure
    1: PreferredLoginDevice
    2: CityTier
    3: WarehouseToHome
    4: PreferredPaymentMode
    5: Gender
    6: HourSpendOnApp
    7: NumberOfDeviceRegistered
    8: PreferedOrderCat
    9: SatisfactionScore
    10: MaritalStatus
    11: NumberOfAddress
    12: Complain
    13: OrderAmountHikeFromlastYear
    14: CouponUsed
    15: OrderCount
    16: DaySinceLastOrder
    17: CashbackAmount
    """

    # ── Order events from UserEvent ───────────────────
    order_events = UserEvent.objects.filter(
        user=user,
        event_type='ORDER'
    ).order_by('-created_at')

    order_count = order_events.count()
    last_order  = order_events.first()

    days_since_last_order = 0
    if last_order:
        delta = dj_timezone.now() - last_order.created_at
        days_since_last_order = delta.days

    # ── Tenure in months ──────────────────────────────
    tenure_days   = (dj_timezone.now() - user.date_joined).days
    tenure_months = max(1, tenure_days // 30)

    # ── Engagement signals from UserEvent ─────────────
    logins = UserEvent.objects.filter(
        user=user,
        event_type='LOGIN'
    ).count()

    # Rough estimate: 1 login session ≈ 0.5 hours on app
    hours_on_app = round(logins * 0.5, 1)

    # Cart adds logged via your CART event
    cart_adds = UserEvent.objects.filter(
        user=user,
        event_type='CART'
    ).count()

    # Wishlist adds
    wishlist_adds = UserEvent.objects.filter(
        user=user,
        event_type='WISHLIST'
    ).count()

    return {
        # ── col 0 ── derived from user.date_joined
        'Tenure':                      tenure_months,

        # ── col 1 ── 0=Mobile Phone, 1=Computer, 2=Phone
        #             default: 0 (mobile, most common in dataset)
        'PreferredLoginDevice':        0,

        # ── col 2 ── 1=Tier1, 2=Tier2, 3=Tier3
        'CityTier':                    1,

        # ── col 3 ── distance in km, default avg from dataset
        'WarehouseToHome':             15,

        # ── col 4 ── 0=Cash on Delivery, 1=CC, 2=DC,
        #             3=E wallet, 4=UPI  — default: 3 (E wallet)
        'PreferredPaymentMode':        3,

        # ── col 5 ── 0=Female, 1=Male — default: 1
        'Gender':                      1,

        # ── col 6 ── derived from login count
        'HourSpendOnApp':              hours_on_app,

        # ── col 7 ── default 1 device
        'NumberOfDeviceRegistered':    1,

        # ── col 8 ── 0=Fashion, 1=Grocery, 2=Laptop&Accessory,
        #             3=Mobile, 4=Mobile Phone, 5=Others
        #             default: 0 (Fashion — matches your store)
        'PreferedOrderCat':            0,

        # ── col 9 ── 1-5 scale, default neutral: 3
        'SatisfactionScore':           3,

        # ── col 10 ── 0=Divorced, 1=Married, 2=Single
        #              default: 2 (Single)
        'MaritalStatus':               2,

        # ── col 11 ── number of saved addresses, default 1
        'NumberOfAddress':             1,

        # ── col 12 ── 0=No complaint, 1=Has complaint
        #              default: 0
        'Complain':                    0,

        # ── col 13 ── % order amount hike vs last year
        #              default avg: 15
        'OrderAmountHikeFromlastYear': 15,

        # ── col 14 ── number of coupons used
        #              update this when you add coupon tracking
        'CouponUsed':                  0,

        # ── col 15 ── from UserEvent ORDER events
        'OrderCount':                  order_count,

        # ── col 16 ── from last ORDER event timestamp
        'DaySinceLastOrder':           days_since_last_order,

        # ── col 17 ── cashback received, default avg: 100
        'CashbackAmount':              100,
    }