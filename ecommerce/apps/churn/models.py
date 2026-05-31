from django.db import models
from django.conf import settings


class UserFeatureSnapshot(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feature_snapshot'
    )

    # Login/activity behavior
    total_logins = models.IntegerField(default=0)

    # Product behavior
    total_product_views = models.IntegerField(default=0)
    total_product_clicks = models.IntegerField(default=0)

    # Cart behavior
    total_cart_adds = models.IntegerField(default=0)
    total_cart_removes = models.IntegerField(default=0)
    cart_abandonment_count = models.IntegerField(default=0)

    # Wishlist behavior
    total_wishlist_adds = models.IntegerField(default=0)
    total_wishlist_removes = models.IntegerField(default=0)

    # Checkout/order behavior
    total_orders = models.IntegerField(default=0)
    checkout_abandonment_count = models.IntegerField(default=0)
    order_cancel_count = models.IntegerField(default=0)
    payment_failed_count = models.IntegerField(default=0)

    # Money behavior
    total_spent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    average_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Review behavior
    review_count = models.IntegerField(default=0)
    average_rating = models.FloatField(default=0)

    # Recency behavior
    days_since_last_login = models.IntegerField(default=999)
    days_since_last_activity = models.IntegerField(default=999)
    days_since_last_order = models.IntegerField(default=999)

    # Ratio/conversion features
    click_to_view_rate = models.FloatField(default=0)
    cart_to_view_rate = models.FloatField(default=0)
    order_to_cart_rate = models.FloatField(default=0)
    wishlist_remove_rate = models.FloatField(default=0)

    # Target label for training
    churn_label = models.BooleanField(default=False)

    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Feature snapshot for {self.user}"


class ChurnPrediction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='churn_predictions'
    )

    probability = models.FloatField()
    prediction = models.BooleanField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        risk = round(self.probability * 100, 2)
        return f"{self.user} - {risk}% churn risk"