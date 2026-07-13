from django.contrib import admin
from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    Coupon,
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
                    'Coupons with a "valid until" date automatically notify users this is a '
                    'limited-time offer (handled by apps.notifications.signals on creation, '
                    'and by the notify_expiring_coupons management command as the actual date '
                    'approaches — no manual admin action needed here).',
            },
        ),
    )

    readonly_fields = [
        'used_count',
    ]

    # NOTE: save_model() used to manually call send_coupon_notifications() and
    # send_offer_expiring_notifications() here, IN ADDITION to the post_save
    # signal in apps/notifications/signals.py already doing the same job.
    # That caused every new coupon to notify + email users twice, and every
    # single edit to an existing limited-time coupon to re-send an "expiring
    # soon" notification (not just on creation, not just near actual expiry).
    # The signal alone is the correct, single source of truth for
    # "notify on new coupon" — it fires from anywhere (admin, shell, API),
    # not just this admin form, and correctly checks `created` so it only
    # runs once. The real "expiring soon" reminder belongs solely in the
    # notify_expiring_coupons scheduled command, which checks actual days
    # remaining rather than firing on every unrelated field edit.