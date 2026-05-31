from django.contrib import admin

from .models import UserFeatureSnapshot, ChurnPrediction


@admin.register(UserFeatureSnapshot)
class UserFeatureSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'total_logins',
        'total_product_views',
        'total_product_clicks',
        'total_cart_adds',
        'total_cart_removes',
        'total_wishlist_adds',
        'total_wishlist_removes',
        'total_orders',
        'cart_abandonment_count',
        'checkout_abandonment_count',
        'days_since_last_order',
        'churn_label',
        'generated_at',
    )

    list_filter = (
        'churn_label',
        'generated_at',
    )

    search_fields = (
        'user__username',
        'user__email',
    )

    ordering = (
        '-generated_at',
    )


@admin.register(ChurnPrediction)
class ChurnPredictionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'probability',
        'prediction',
        'created_at',
    )

    list_filter = (
        'prediction',
        'created_at',
    )

    search_fields = (
        'user__username',
        'user__email',
    )

    ordering = (
        '-created_at',
    )