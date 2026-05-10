from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.

    Always use this instead of Django's default User model because:
    - It is flexible for future extensions
    - Avoids painful migrations later if you need custom fields
    """

    # Email is unique to support login identification, retention campaigns, and recommendations
    email = models.EmailField(unique=True)

    # Optional phone number for future SMS-based notifications, offers, and retention campaigns
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    # Optional profile image stored in MEDIA_ROOT/profiles/
    profile_image = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True
    )

    # Automatically stores when the user account was created (useful for analytics & churn tracking)
    created_at = models.DateTimeField(auto_now_add=True)

    # Automatically updates whenever the user record is modified
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        """
        Returns full name if available, otherwise falls back to username.
        Useful for dashboards, emails, and personalization.
        """
        return f"{self.first_name} {self.last_name}".strip() or self.username