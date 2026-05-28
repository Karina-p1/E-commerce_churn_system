from django.db import models
from django.conf import settings
from apps.products.models import Product


class UserEvent(models.Model):

    EVENT_CHOICES = (

        ('LOGIN','Login'),
        ('LOGOUT','Logout'),
        ('VIEW','View'),
        ('CLICK','Click'),
        ('CART','Cart'),
        ('REMOVE_CART','Remove Cart'),
        ('WISHLIST','Wishlist'),
        ('ORDER','Order'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    product=models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    event_type=models.CharField(
        max_length=30,
        choices=EVENT_CHOICES
    )

    created_at=models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f"{self.user} - {self.event_type}"