from django.db import models
from django.conf import settings

class ChurnScore(models.Model):
    RISK_LEVELS = [
        ('low',  'Low'),
        ('high', 'High'),
    ]
    customer     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='churn_scores'
    )
    score        = models.FloatField()
    risk_level   = models.CharField(max_length=10, choices=RISK_LEVELS)
    predicted_at = models.DateTimeField(auto_now_add=True)
    is_churned   = models.BooleanField(null=True, blank=True)

    # Explains WHY risk_level is 'high' when the model's own score is low —
    # e.g. "Inactive 45+ days with a thin order history". Set by an
    # override rule in predictor.py; blank when the model's own score
    # already agrees with the final risk_level (no override needed).
    override_reason = models.CharField(max_length=255, blank=True, null=True)

    # ── Audit trail (added) ─────────────────────────────────────────
    # Stored with every score so the history chart is explainable later:
    # you can see exactly which inputs produced each point, what the raw
    # model said before any override, and which features drove it.
    # Null on rows created before this migration.
    features    = models.JSONField(null=True, blank=True)   # raw inputs used
    model_score = models.FloatField(null=True, blank=True)  # un-overridden model output
    top_factors = models.JSONField(null=True, blank=True)   # SHAP explanation

    class Meta:
        ordering = ['-predicted_at']

    def __str__(self):
        return f"{self.customer.username} — {self.risk_level} ({self.score:.2f})"

    @property
    def risk_badge_color(self):
        return {'high': 'red', 'medium': 'orange', 'low': 'green'}[self.risk_level]


class UserFeatureSnapshot(models.Model):
    user                       = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feature_snapshot'
    )
    total_logins               = models.IntegerField(default=0)
    total_product_views        = models.IntegerField(default=0)
    total_product_clicks       = models.IntegerField(default=0)
    total_cart_adds            = models.IntegerField(default=0)
    total_cart_removes         = models.IntegerField(default=0)
    cart_abandonment_count     = models.IntegerField(default=0)
    total_wishlist_adds        = models.IntegerField(default=0)
    total_wishlist_removes     = models.IntegerField(default=0)
    total_orders               = models.IntegerField(default=0)
    checkout_abandonment_count = models.IntegerField(default=0)
    order_cancel_count         = models.IntegerField(default=0)
    payment_failed_count       = models.IntegerField(default=0)
    total_spent                = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    average_order_value        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    review_count               = models.IntegerField(default=0)
    average_rating             = models.FloatField(default=0)
    days_since_last_login      = models.IntegerField(default=999)
    days_since_last_activity   = models.IntegerField(default=999)
    days_since_last_order      = models.IntegerField(default=999)
    click_to_view_rate         = models.FloatField(default=0)
    cart_to_view_rate          = models.FloatField(default=0)
    order_to_cart_rate         = models.FloatField(default=0)
    wishlist_remove_rate       = models.FloatField(default=0)
    churn_label                = models.BooleanField(default=False)
    generated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Features — {self.user}"


class ChurnPrediction(models.Model):
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='churn_predictions'
    )
    probability = models.FloatField()
    prediction  = models.BooleanField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} — {round(self.probability * 100, 1)}% churn risk"

class RetentionCampaign(models.Model):
    """
    One closed-loop churn intervention.

    Flow:
        high-risk score
        -> private win-back coupon + notification
        -> customer returns
        -> paid order is recorded
        -> customer is re-scored
        -> before/after churn risk is compared
    """

    STATUS_CHOICES = [
        ('SENT', 'Sent'),
        ('VIEWED', 'Viewed'),
        ('RECOVERED', 'Customer Returned'),
        ('EXPIRED', 'Expired / No Response'),
    ]

    OUTCOME_CHOICES = [
        ('PENDING', 'Pending'),
        ('RISK_REDUCED', 'Recovered + Risk Reduced'),
        ('IMPROVED_STILL_HIGH', 'Returned but Still High Risk'),
        ('RETURNED_NO_IMPROVEMENT', 'Returned but Risk Did Not Improve'),
        ('EXPIRED', 'Expired / No Response'),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='retention_campaigns',
    )

    source_score = models.ForeignKey(
        'ChurnScore',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_retention_campaigns',
        help_text='Saved churn score that triggered this campaign.',
    )

    coupon = models.ForeignKey(
        'orders.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retention_campaigns',
    )

    notification = models.ForeignKey(
        'notifications.Notification',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retention_campaigns',
    )

    before_score = models.FloatField()
    before_risk_level = models.CharField(max_length=10)

    after_score = models.FloatField(null=True, blank=True)
    after_risk_level = models.CharField(max_length=10, blank=True)

    # after_score - before_score.
    # Negative = churn risk decreased.
    score_change = models.FloatField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SENT',
    )

    outcome = models.CharField(
        max_length=30,
        choices=OUTCOME_CHOICES,
        default='PENDING',
    )

    sent_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    rescored_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    recovered_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retention_recoveries',
    )

    recovered_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    # True only when the paid return order used this exact WEMISSYOU coupon.
    used_campaign_coupon = models.BooleanField(default=False)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return (
            f"Retention — {self.customer.username} — "
            f"{self.get_status_display()}"
        )

    @property
    def risk_reduced(self):
        return (
            self.after_score is not None
            and self.after_score < self.before_score
        )

    @property
    def product_summary(self):
        """
        Human-friendly product names for the recovered order.

        Example:
            "Wireless Headphones"
            "Wireless Headphones, Phone Case + 2 more"

        We deliberately show product names in the UI instead of "Order #241".
        """
        if not self.recovered_order_id:
            return "—"

        names = [
            item.product_name
            for item in self.recovered_order.items.all()
            if item.product_name
        ]

        if not names:
            return "Purchased products"

        if len(names) <= 2:
            return ", ".join(names)

        return f"{names[0]}, {names[1]} + {len(names) - 2} more"
