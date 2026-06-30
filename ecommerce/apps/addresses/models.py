from django.conf import settings
from django.db import models


class Address(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses"
    )

    label = models.CharField(
        max_length=30,
        default="Home"
    )

    full_name = models.CharField(
        max_length=150
    )

    phone = models.CharField(
        max_length=20
    )

    province = models.CharField(
        max_length=100
    )

    district = models.CharField(
        max_length=100
    )

    city = models.CharField(
        max_length=100
    )

    ward = models.CharField(
        max_length=20
    )

    street = models.CharField(
        max_length=255
    )

    landmark = models.CharField(
        max_length=255,
        blank=True
    )

    latitude = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    is_default = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):

        if self.is_default:

            Address.objects.filter(
                user=self.user
            ).update(
                is_default=False
            )

        super().save(*args, **kwargs)

    def __str__(self):

        return f"{self.user.username} - {self.label}"