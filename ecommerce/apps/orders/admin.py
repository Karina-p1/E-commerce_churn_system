from django.contrib import admin
from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    Coupon,
)

# NEW
from apps.notifications.services import (
    send_coupon_notifications,
    send_offer_expiring_notifications,
)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_items', 'total_price', 'updated_at']
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'total_price', 'created_at']
    list_filter = ['status']
    list_editable = ['status']
    inlines = [OrderItemInline]


admin.site.register(OrderStatusHistory)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'coupon_type',
        'discount_type',
        'discount_value',
        'min_order_amount',
        'max_uses',
        'used_count',
        'is_active',
        'is_limited_time_offer',
    ]

    list_filter = [
        'coupon_type',
        'discount_type',
        'is_active',
    ]

    search_fields = [
        'code',
    ]

    fieldsets = (
        (
            'Basic',
            {
                'fields': (
                    'code',
                    'coupon_type',
                    'is_active',
                )
            },
        ),

        (
            'Standard Discount',
            {
                'fields': (
                    'discount_type',
                    'discount_value',
                    'min_order_amount',
                ),
                'description':
                    'Used by STANDARD and FIRST_ORDER coupons.',
            },
        ),

        (
            'Minimum Quantity Rule',
            {
                'fields': (
                    'min_quantity',
                ),
                'description':
                    'Only used for MIN_QUANTITY coupons.',
            },
        ),

        (
            'Buy X Get Y Rule',
            {
                'fields': (
                    'buy_quantity',
                    'get_quantity',
                    'get_discount_percent',
                ),
                'description':
                    'Only used for BUY_X_GET_Y coupons.',
            },
        ),

        (
            'Usage Limits & Validity',
            {
                'fields': (
                    'max_uses',
                    'used_count',
                    'valid_from',
                    'valid_until',
                ),
                'description':
                    'Coupons with a valid until date will also notify users that the offer is limited.',
            },
        ),
    )

    readonly_fields = [
        'used_count',
    ]

    def save_model(self, request, obj, form, change):
        """
        Automatically notify all registered users whenever
        a NEW coupon is created.

        Also sends Limited-Time Offer notifications if
        the coupon has a valid_until date.
        """

        is_new = obj.pk is None

        super().save_model(request, obj, form, change)

        # Notify only when creating a new coupon
        if is_new:
            send_coupon_notifications(obj)

        # Notify users about limited-time offers
        if obj.valid_until:
            send_offer_expiring_notifications(obj)