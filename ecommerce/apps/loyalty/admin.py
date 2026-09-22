from django.contrib import admin

from .models import (
    LoyaltyTier,
    LoyaltyAccount,
    LoyaltyTransaction,
    LoyaltyPromotion,
    LoyaltyPromotionAccess,
)


@admin.register(LoyaltyTier)
class LoyaltyTierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "minimum_points",
        "points_multiplier",
        "discount_percentage",
        "early_access_hours",
        "exclusive_offers",
        "free_shipping",
        "support_priority",
        "is_active",
    )

    list_filter = (
        "is_active",
        "exclusive_offers",
        "free_shipping",
        "support_priority",
    )

    ordering = ("minimum_points",)


@admin.register(LoyaltyAccount)
class LoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "current_tier",
        "available_points",
        "lifetime_points_earned",
        "lifetime_points_redeemed",
        "updated_at",
    )

    list_filter = (
        "current_tier",
    )

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "transaction_type",
        "points",
        "balance_after",
        "order",
        "created_at",
    )

    list_filter = (
        "transaction_type",
        "created_at",
    )

    search_fields = (
        "account__user__username",
        "account__user__email",
        "description",
    )

    readonly_fields = (
        "created_at",
    )


@admin.register(LoyaltyPromotion)
class LoyaltyPromotionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product",
        "public_start",
        "end_time",
        "bonus_points",
        "discount_percentage",
        "is_exclusive",
        "is_active",
    )

    list_filter = (
        "is_active",
        "is_exclusive",
        "free_shipping",
    )

    search_fields = (
        "name",
        "product__name",
    )


@admin.register(LoyaltyPromotionAccess)
class LoyaltyPromotionAccessAdmin(admin.ModelAdmin):
    list_display = (
        "promotion",
        "tier",
        "access_start",
    )

    list_filter = (
        "tier",
    )