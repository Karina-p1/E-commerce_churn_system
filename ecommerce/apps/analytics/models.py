from django.db import models

# Create your models here.
from django.db import models


class RevenueSnapshot(models.Model):

    date = models.DateField(unique=True)

    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    total_orders = models.PositiveIntegerField(default=0)

    average_order_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    esewa_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    cod_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return str(self.date)
    
class RevenueSummary(models.Model):

    total_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    total_orders = models.PositiveIntegerField(default=0)

    average_order_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    esewa_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    cod_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Revenue Summary"