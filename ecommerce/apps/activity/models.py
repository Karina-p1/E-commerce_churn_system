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
    
    @property
    def active_time(self):
        hours = self.active_seconds // 3600
        minutes = (self.active_seconds % 3600) // 60
        seconds = self.active_seconds % 60

        return f"{hours}h {minutes}m {seconds}s"
    
    # @property
    # def active_hours(self):
    #     return round(self.active_seconds / 3600, 2)

    @property
    def is_open(self):
        """True when this analytics session has not been explicitly closed."""
        return self.ended_at is None

    def is_stale(self, timeout_seconds=120):
        """True when an open session has exceeded the inactivity window."""
        if self.ended_at is not None:
            return False
        return (timezone.now() - self.last_activity).total_seconds() >= timeout_seconds

    def close(self, ended_at=None):
        """Close this analytics session once without altering active_seconds."""
        if self.ended_at is None:
            self.ended_at = ended_at or timezone.now()
            self.save(update_fields=["ended_at"])

    def __str__(self):
        return f"{self.user.username} - {self.started_at}"
