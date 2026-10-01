from django import forms
from django.core.exceptions import ValidationError

from ecommerce.validators import (
    validate_name,
    validate_phone,
    validate_text,
)

from .models import Address


class AddressForm(forms.ModelForm):

    def clean_label(self):
        return validate_text(
            self.cleaned_data.get("label"),
            "Label",
            min_length=2,
            max_length=30,
        )

    def clean_full_name(self):
        return validate_name(
            self.cleaned_data.get("full_name"),
            "Full name",
            max_length=150,
        )

    def clean_phone(self):
        return validate_phone(
            self.cleaned_data.get("phone"),
            field_name="Phone number",
        )

    def clean_province(self):
        return validate_text(
            self.cleaned_data.get("province"),
            "Province",
            min_length=2,
            max_length=100,
        )

    def clean_district(self):
        return validate_text(
            self.cleaned_data.get("district"),
            "District",
            min_length=2,
            max_length=100,
        )

    def clean_city(self):
        return validate_text(
            self.cleaned_data.get("city"),
            "City",
            min_length=2,
            max_length=100,
        )

    def clean_ward(self):
        """
        Nepali wards are numbered, not named, so a ward is either a valid
        ward number (1-99) or a ward name — but "0" or "13.5" is neither.
        """
        ward = validate_text(
            self.cleaned_data.get("ward"),
            "Ward",
            min_length=1,
            max_length=20,
        )

        if ward.isdigit():
            number = int(ward)

            if not (1 <= number <= 99):
                raise ValidationError("Ward must be between 1 and 99.")

        return ward

    def clean_street(self):
        return validate_text(
            self.cleaned_data.get("street"),
            "Street",
            min_length=3,
            max_length=255,
        )

    def clean_landmark(self):
        return validate_text(
            self.cleaned_data.get("landmark"),
            "Landmark",
            required=False,
            max_length=255,
        )

    def clean_latitude(self):
        latitude = self.cleaned_data.get("latitude")

        if latitude is not None and not (-90 <= latitude <= 90):
            raise ValidationError("Latitude must be between -90 and 90.")

        return latitude

    def clean_longitude(self):
        longitude = self.cleaned_data.get("longitude")

        if longitude is not None and not (-180 <= longitude <= 180):
            raise ValidationError("Longitude must be between -180 and 180.")

        return longitude

    def clean(self):
        """
        The map picker writes both coordinates or neither, so a half-filled
        pair means the pick failed and the delivery pin would land in the
        wrong place.
        """
        cleaned_data = super().clean()

        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if (latitude is None) != (longitude is None):
            self.add_error(
                "latitude",
                "Pick the delivery location on the map so both "
                "latitude and longitude are set.",
            )

        return cleaned_data

    class Meta:
        model = Address

        exclude = (
            "user",
            "is_default",
            "created_at",
        )

        widgets = {
            "label": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Home / Office / Hostel",
                "minlength": 2,
                "maxlength": 30,
            }),

            "full_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "As it appears on your ID",
                "minlength": 2,
                "maxlength": 150,
            }),

            "phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "9812345678",
                "inputmode": "numeric",
                "data-fv-phone": "1",
                "maxlength": 20,
            }),

            "province": forms.TextInput(attrs={
                "class": "form-control",
                "minlength": 2,
                "maxlength": 100,
            }),

            "district": forms.TextInput(attrs={
                "class": "form-control",
                "minlength": 2,
                "maxlength": 100,
            }),

            "city": forms.TextInput(attrs={
                "class": "form-control",
                "minlength": 2,
                "maxlength": 100,
            }),

            "ward": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 4",
                "minlength": 1,
                "maxlength": 20,
            }),

            "street": forms.TextInput(attrs={
                "class": "form-control",
                "minlength": 3,
                "maxlength": 255,
            }),

            "landmark": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": 255,
            }),

            "latitude": forms.HiddenInput(),

            "longitude": forms.HiddenInput(),
        }
