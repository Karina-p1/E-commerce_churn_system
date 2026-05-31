from django.db import models
from django.conf import settings


class ChurnScore(models.Model):

    RISK_LEVELS = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    customer = models.ForeignKey(
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