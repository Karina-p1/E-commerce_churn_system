from django.db import models
from django.conf import settings
from apps.products.models import Product
from django.utils import timezone


class UserEvent(models.Model):

    EVENT_CHOICES = (
    ('LOGIN', 'Login'),
    ('LOGOUT', 'Logout'),

    ('VIEW', 'Product View'),
    ('CLICK', 'Product Click'),

    ('CART', 'Add To Cart'),
    ('REMOVE_CART', 'Remove From Cart'),

    ('WISHLIST', 'Add To Wishlist'),
    ('REMOVE_WISHLIST', 'Remove From Wishlist'),

    ('CHECKOUT_STARTED', 'Checkout Started'),
    ('CART_ABANDONED', 'Cart Abandoned'),
    
    ('PAYMENT_STARTED', 'Payment Started'),
    ('PAYMENT_SUCCESS', 'Payment Success'),
    ('PAYMENT_FAILED', 'Payment Failed'),

    ('ORDER', 'Order Placed'),
    ('ORDER_CANCELLED', 'Order Cancelled'),
    
    ('REVIEW', 'Review'),
)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_events'
    )

    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='activity_events'
    )

    event_type = models.CharField(
        max_length=30,
        choices=EVENT_CHOICES,
        db_index=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'event_type']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['product', 'event_type']),
        ]

    def __str__(self):
        return f"{self.user} - {self.event_type}"
    
class UserSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions"
    )

    started_at = models.DateTimeField(auto_now_add=True)

    last_activity = models.DateTimeField(
        default=timezone.now
    )

    active_seconds = models.PositiveIntegerField(default=0)

    ended_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.started_at}"
