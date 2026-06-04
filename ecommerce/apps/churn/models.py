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