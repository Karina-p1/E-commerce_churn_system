from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
)

from .models import User


# =========================================================
# Shared validation helpers
# =========================================================

def validate_name(value):
    value = value.strip()

    if len(value) < 2:
        raise forms.ValidationError(
            "Name must contain at least 2 characters."
        )

    # Allows names such as:
    # Preeti
    # Anne-Marie
    # O'Connor
    # Mary Jane
    allowed = set(" -'")

    if not all(char.isalpha() or char in allowed for char in value):
        raise forms.ValidationError(
            "Name can only contain letters, spaces, hyphens, and apostrophes."
        )

    return value


def validate_phone(value):
    value = value.strip()

    if not value:
        return value

    # Remove characters commonly used for formatting.
    normalized = (
        value.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if normalized.startswith("+"):
        digits = normalized[1:]
    else:
        digits = normalized

    if not digits.isdigit():
        raise forms.ValidationError(
            "Enter a valid phone number."
        )

    if len(digits) < 7 or len(digits) > 15:
        raise forms.ValidationError(
            "Phone number must contain between 7 and 15 digits."
        )

    return value


# =========================================================
# Registration
# =========================================================

class RegisterForm(UserCreationForm):

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your email",
        })
    )

    first_name = forms.CharField(
        required=True,
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "First name",
        })
    )

    last_name = forms.CharField(
        required=True,
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Last name",
        })
    )

    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Phone number (optional)",
        })
    )

    gender = forms.ChoiceField(
        required=True,
        choices=User.GENDER_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-control",
        })
    )

    marital_status = forms.ChoiceField(
        required=True,
        choices=User.MARITAL_STATUS_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-control",
        })
    )

    class Meta:
        model = User

        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "gender",
            "marital_status",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = "form-control"

    # -----------------------------------------------------
    # Email
    # -----------------------------------------------------

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email is already registered."
            )

        return email

    # -----------------------------------------------------
    # First name
    # -----------------------------------------------------

    def clean_first_name(self):
        return validate_name(
            self.cleaned_data.get("first_name", "")
        )

    # -----------------------------------------------------
    # Last name
    # -----------------------------------------------------

    def clean_last_name(self):
        return validate_name(
            self.cleaned_data.get("last_name", "")
        )

    # -----------------------------------------------------
    # Phone
    # -----------------------------------------------------

    def clean_phone_number(self):
        return validate_phone(
            self.cleaned_data.get("phone_number", "")
        )


# =========================================================
# Login
# =========================================================

class LoginForm(AuthenticationForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Username",
        })

        self.fields["password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Password",
        })


# =========================================================
# Profile update
# =========================================================

class ProfileUpdateForm(forms.ModelForm):

    class Meta:
        model = User

        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "profile_image",
            "gender",
            "marital_status",
            "email_notifications_enabled",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():

            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"

            else:
                field.widget.attrs["class"] = "form-control"

    # -----------------------------------------------------
    # Email
    # -----------------------------------------------------

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if not email:
            raise forms.ValidationError(
                "Email address is required."
            )

        duplicate = User.objects.filter(
            email__iexact=email
        )

        # IMPORTANT:
        # Don't consider the currently logged-in user's
        # existing email to be a duplicate.
        if self.instance.pk:
            duplicate = duplicate.exclude(
                pk=self.instance.pk
            )

        if duplicate.exists():
            raise forms.ValidationError(
                "This email is already registered to another account."
            )

        return email

    # -----------------------------------------------------
    # First name
    # -----------------------------------------------------

    def clean_first_name(self):
        return validate_name(
            self.cleaned_data.get("first_name", "")
        )

    # -----------------------------------------------------
    # Last name
    # -----------------------------------------------------

    def clean_last_name(self):
        return validate_name(
            self.cleaned_data.get("last_name", "")
        )

    # -----------------------------------------------------
    # Phone
    # -----------------------------------------------------

    def clean_phone_number(self):
        return validate_phone(
            self.cleaned_data.get("phone_number", "")
        )

    # -----------------------------------------------------
    # Profile image
    # -----------------------------------------------------

    def clean_profile_image(self):
        image = self.cleaned_data.get("profile_image")

        if not image:
            return image

        # Existing image objects during profile editing
        # don't necessarily represent a newly uploaded file.
        if not hasattr(image, "size"):
            return image

        max_size = 5 * 1024 * 1024  # 5 MB

        if image.size > max_size:
            raise forms.ValidationError(
                "Profile image must be 5 MB or smaller."
            )

        content_type = getattr(
            image,
            "content_type",
            None
        )

        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if content_type and content_type not in allowed_types:
            raise forms.ValidationError(
                "Only JPG, PNG, and WEBP images are allowed."
            )

        return image