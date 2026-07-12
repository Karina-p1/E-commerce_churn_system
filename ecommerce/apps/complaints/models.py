from django.db import models
from django.conf import settings
from django.utils import timezone


class Complaint(models.Model):

    COMPLAINT_TYPES = [
        ("PAYMENT", "Payment Issue"),
        ("PRODUCT", "Product Issue"),
        ("DELIVERY", "Delivery Issue"),
        ("INTERFACE", "Website/App Interface"),
        ("REFUND", "Return & Refund"),
        ("SERVICE", "Customer Service"),
        ("OTHER", "Other"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("IN_PROGRESS", "In Progress"),
        ("RESOLVED", "Resolved"),
        ("REJECTED", "Rejected"),
    ]

    SATISFACTION_CHOICES = [
        (1, "1 ⭐"),
        (2, "2 ⭐⭐"),
        (3, "3 ⭐⭐⭐"),
        (4, "4 ⭐⭐⭐⭐"),
        (5, "5 ⭐⭐⭐⭐⭐"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="complaints"
    )

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaints"
    )

    complaint_type = models.CharField(
        max_length=20,
        choices=COMPLAINT_TYPES
    )

    subject = models.CharField(max_length=255)

    description = models.TextField()

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="MEDIUM"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    admin_reply = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="complaints/",
        blank=True,
        null=True
    )

    # NEW
    customer_rating = models.PositiveSmallIntegerField(
        choices=SATISFACTION_CHOICES,
        blank=True,
        null=True
    )

    # NEW
    customer_feedback = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    resolved_at = models.DateTimeField(
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):

        if self.status == "RESOLVED" and self.resolved_at is None:
            self.resolved_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def resolution_days(self):

        if self.resolved_at:
            return (self.resolved_at - self.created_at).days

        return None

    def __str__(self):
        return f"{self.user.username} - {self.subject}"