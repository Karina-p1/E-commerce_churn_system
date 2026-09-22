from django.contrib import admin
from django.utils.html import format_html
from .models import ChurnScore, UserFeatureSnapshot, ChurnPrediction


@admin.register(ChurnScore)
class ChurnScoreAdmin(admin.ModelAdmin):
    list_display    = ('customer', 'risk_badge', 'score', 'override_reason', 'predicted_at')
    list_filter     = ('risk_level',)
    search_fields   = ('customer__username', 'customer__email')
    ordering        = ('-score',)
    # override_reason added here too — it's set by predictor.py, never
    # hand-edited by an admin, same as score/risk_level.
    readonly_fields = ('customer', 'score', 'risk_level', 'override_reason', 'predicted_at')

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


# ── DEPRECATED ──────────────────────────────────────────────────────
# UserFeatureSnapshot and ChurnPrediction are not written to or read
# from anywhere in features.py, predictor.py, services.py, or
# views.py. They appear to be leftovers from an earlier design
# (before features were computed live on every scoring run) and are
# currently dead tables — registered here only so existing data, if
# any, remains visible/removable via admin. Confirm with the team
# whether these are safe to drop (model + migration) before the exam,
# or whether something outside apps/churn still depends on them.

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