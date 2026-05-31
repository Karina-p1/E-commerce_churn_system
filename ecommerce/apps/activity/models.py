from django.db import models
from django.conf import settings
from apps.products.models import Product


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

    ('ORDER', 'Order Placed'),
    ('ORDER_CANCELLED', 'Order Cancelled'),
    ('PAYMENT_FAILED', 'Payment Failed'),

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