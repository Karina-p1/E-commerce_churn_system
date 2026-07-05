from django import forms
from .models import RefundRequest


class RefundRequestForm(forms.ModelForm):

    class Meta:
        model = RefundRequest

        fields = [
            "reason",
            "other_reason",
            "bank_name",
            "account_holder",
            "account_number",
            "branch",
            "phone",
        ]

        widgets = {

            "reason": forms.Select(attrs={
                "class": "form-select"
            }),

            "other_reason": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3
            }),

            "bank_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "NIC Asia, Global IME..."
            }),

            "account_holder": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "account_number": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "branch": forms.TextInput(attrs={
                "class": "form-control"
            }),

            "phone": forms.TextInput(attrs={
                "class": "form-control"
            }),
        }