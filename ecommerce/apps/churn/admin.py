from django.contrib import admin
from django.utils.html import format_html
from .models import ChurnScore, UserFeatureSnapshot, ChurnPrediction


@admin.register(ChurnScore)
class ChurnScoreAdmin(admin.ModelAdmin):
    list_display    = ('customer', 'risk_badge', 'score', 'predicted_at')
    list_filter     = ('risk_level',)
    search_fields   = ('customer__username', 'customer__email')
    ordering        = ('-score',)
    readonly_fields = ('customer', 'score', 'risk_level', 'predicted_at')

    def risk_badge(self, obj):
        if obj.risk_level == 'high':
            color, label = '#dc2626', 'HIGH RISK'
        else:
            color, label = '#16a34a', 'LOW RISK'
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:4px; font-weight:bold; font-size:11px;">{}</span>',
            color, label
        )
    risk_badge.short_description = 'Risk'


@admin.register(UserFeatureSnapshot)
class UserFeatureSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'total_logins', 'total_product_views',
        'total_product_clicks', 'total_cart_adds', 'total_cart_removes',
        'total_wishlist_adds', 'total_wishlist_removes', 'total_orders',
        'cart_abandonment_count', 'checkout_abandonment_count',
        'days_since_last_order', 'churn_label', 'generated_at',
    )
    list_filter   = ('churn_label', 'generated_at')
    search_fields = ('user__username', 'user__email')
    ordering      = ('-generated_at',)


@admin.register(ChurnPrediction)
class ChurnPredictionAdmin(admin.ModelAdmin):
    list_display  = ('user', 'probability', 'prediction', 'created_at')
    list_filter   = ('prediction', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering      = ('-created_at',)