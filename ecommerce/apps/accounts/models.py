from django.contrib.auth.models import AbstractUser
from django.db import models

# The User model extends Django's AbstractUser to include additional fields such as email, phone number, profile image, and timestamps for creation and updates.


class User(AbstractUser):
    # The email field is defined as an EmailField and is set to be unique, ensuring that no two users can have the same email address. useful for login retention campaigns recommendations
    email = models.EmailField(unique=True)
# The phone_number field is defined as a CharField with a maximum length of 20 characters. It is optional, allowing users to leave it blank or null if they choose not to provide a phone number.Future use: SMS offers retention notifications
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )
# The profile_image field is defined as an ImageField, which allows users to upload a profile picture. The uploaded images will be stored in the 'profiles/' directory. This field is also optional, allowing users to leave it blank or null if they choose not to upload a profile image.
    profile_image = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True
    )
# The created_at field is a DateTimeField that automatically sets the current date and time when a new user is created. This allows you to track when each user account was created.
    created_at = models.DateTimeField(auto_now_add=True)
# The updated_at field is a DateTimeField that automatically updates to the current date and time whenever the user object is saved. This allows you to track when each user account was last updated.
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username
