from django.db import models
from django.conf import settings


class Notification(models.Model):
    NOTIF_TYPE_CHOICES = [
        ('COUPON', 'New Coupon'),
        ('OFFER_EXPIRING', 'Offer Expiring Soon'),
        ('GENERAL', 'General'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notif_type = models.CharField(
        max_length=20,
        choices=NOTIF_TYPE_CHOICES,
        default='GENERAL'
    )
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=300)

    # String reference avoids a hard import dependency on apps.orders.
    coupon = models.ForeignKey(
        'orders.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient.username} — {self.title}"