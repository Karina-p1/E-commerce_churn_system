from django.contrib import admin
from .models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Coupon

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
    list_filter = ['coupon_type', 'discount_type', 'is_active']
    search_fields = ['code']
    fieldsets = (
        ('Basic', {
            'fields': ('code', 'coupon_type', 'is_active')
        }),
        ('Standard discount', {
            'fields': ('discount_type', 'discount_value', 'min_order_amount'),
            'description': 'Used by STANDARD and FIRST_ORDER types.',
        }),
        ('Minimum quantity rule', {
            'fields': ('min_quantity',),
            'description': 'Used only by the MIN_QUANTITY type.',
        }),
        ('Buy X get Y rule', {
            'fields': ('buy_quantity', 'get_quantity', 'get_discount_percent'),
            'description': 'Used only by the BUY_X_GET_Y type.',
        }),
        ('Usage limits & validity', {
            'fields': ('max_uses', 'used_count', 'valid_from', 'valid_until'),
            'description': 'Setting "valid until" marks this as a limited-time offer '
                            'and triggers the expiring-offer notification job.',
        }),
    )
    readonly_fields = ['used_count']