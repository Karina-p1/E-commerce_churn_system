from django import forms
from .models import Address


class AddressForm(forms.ModelForm):

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
                "placeholder": "Home / Office / Hostel"
            }),

            "full_name": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "phone": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "province": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "district": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "city": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "ward": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "street": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "landmark": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "latitude": forms.HiddenInput(),

            "longitude": forms.HiddenInput(),
        }