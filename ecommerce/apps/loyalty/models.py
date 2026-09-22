from django.db import models

# Create your models here.
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.orders.models import Order
from apps.products.models import Product


class LoyaltyTier(models.Model):
    """
    Defines a customer's loyalty level and its benefits.
    """

    SUPPORT_PRIORITY_CHOICES = [
        ("NORMAL", "Normal"),
        ("HIGH", "High"),
        ("URGENT", "Urgent"),
    ]

    name = models.CharField(
        max_length=30,
        unique=True
    )

    minimum_points = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )

    points_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(0)]
    )

    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)]
    )

    early_access_hours = models.PositiveIntegerField(
        default=0
    )

    exclusive_offers = models.BooleanField(
        default=False
    )

    free_shipping = models.BooleanField(
        default=False
    )

    support_priority = models.CharField(
        max_length=10,
        choices=SUPPORT_PRIORITY_CHOICES,
        default="NORMAL"
    )

    description = models.TextField(
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["minimum_points"]

    def __str__(self):
        return self.name


class LoyaltyAccount(models.Model):
    """
    Stores the loyalty information for one customer.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="loyalty_account"
    )

    current_tier = models.ForeignKey(
        LoyaltyTier,
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
        blank=True
    )

    available_points = models.PositiveIntegerField(
        default=0
    )

    lifetime_points_earned = models.PositiveIntegerField(
        default=0
    )

    lifetime_points_redeemed = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-lifetime_points_earned"]

    def __str__(self):
        tier = self.current_tier.name if self.current_tier else "No Tier"
        return f"{self.user} - {tier} - {self.available_points} points"


class LoyaltyTransaction(models.Model):
    """
    Records every change to a customer's loyalty points.
    """

    TRANSACTION_TYPE_CHOICES = [
        ("PURCHASE", "Purchase"),
        ("FIRST_PURCHASE", "First Purchase"),
        ("REVIEW", "Review Reward"),
        ("REFERRAL", "Referral"),
        ("BONUS", "Bonus"),
        ("REDEMPTION", "Redemption"),
        ("REFUND_REVERSAL", "Refund Reversal"),
        ("ADMIN_ADJUSTMENT", "Admin Adjustment"),
    ]

    account = models.ForeignKey(
        LoyaltyAccount,
        on_delete=models.CASCADE,
        related_name="transactions"
    )

    transaction_type = models.CharField(
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES
    )

    points = models.IntegerField(
        validators=[MinValueValidator(-1000000)]
    )

    balance_after = models.PositiveIntegerField(
        default=0
    )

    description = models.CharField(
        max_length=255,
        blank=True
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_transactions"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["order", "transaction_type"],
                condition=models.Q(transaction_type="PURCHASE"),
                name="unique_purchase_loyalty_transaction_per_order",
            )
        ]

    def __str__(self):
        return (
            f"{self.account.user} | "
            f"{self.transaction_type} | "
            f"{self.points:+d} points"
        )


class LoyaltyPromotion(models.Model):
    """
    A loyalty-related promotion attached to an existing product.

    The product itself is NOT duplicated. A promotion controls
    special loyalty access, discounts, bonuses, etc.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="loyalty_promotions"
    )

    name = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True
    )

    public_start = models.DateTimeField()

    end_time = models.DateTimeField()

    bonus_points = models.PositiveIntegerField(
        default=0
    )

    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)]
    )

    free_shipping = models.BooleanField(
        default=False
    )

    is_exclusive = models.BooleanField(
        default=False
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-public_start"]

    def __str__(self):
        return f"{self.name} - {self.product.name}"


class LoyaltyPromotionAccess(models.Model):
    """
    Defines when a particular loyalty tier can access a promotion.

    Example:

    Platinum -> Sep 28, 10 AM
    Gold     -> Sep 29, 10 AM
    Public   -> Sep 30, 10 AM
    """

    promotion = models.ForeignKey(
        LoyaltyPromotion,
        on_delete=models.CASCADE,
        related_name="tier_access"
    )

    tier = models.ForeignKey(
        LoyaltyTier,
        on_delete=models.CASCADE,
        related_name="promotion_access"
    )

    access_start = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "tier"],
                name="unique_promotion_tier_access"
            )
        ]

        ordering = ["access_start"]

    def __str__(self):
        return (
            f"{self.promotion.name} | "
            f"{self.tier.name} | "
            f"{self.access_start}"
        )