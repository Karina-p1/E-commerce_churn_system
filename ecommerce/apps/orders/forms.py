from django import forms

from ecommerce.validators import (
    validate_digits,
    validate_name,
    validate_phone,
    validate_text,
)

from .models import RefundRequest


class RefundRequestForm(forms.ModelForm):

    def clean_reason(self):
        return validate_text(
            self.cleaned_data.get("reason"),
            "Reason",
            max_length=30,
        )

    def clean_other_reason(self):
        return validate_text(
            self.cleaned_data.get("other_reason"),
            "Other reason",
            required=False,
            min_length=10,
            max_length=1000,
        )

    def clean_bank_name(self):
        return validate_text(
            self.cleaned_data.get("bank_name"),
            "Bank name",
            min_length=2,
            max_length=120,
        )

    def clean_account_holder(self):
        return validate_name(
            self.cleaned_data.get("account_holder"),
            field_name="Account holder",
            max_length=120,
        )

    def clean_account_number(self):
        return validate_digits(
            self.cleaned_data.get("account_number"),
            "Account number",
            min_length=4,
            max_length=50,
        )

    def clean_branch(self):
        return validate_text(
            self.cleaned_data.get("branch"),
            "Branch",
            required=False,
            max_length=120,
        )

    def clean_phone(self):
        return validate_phone(
            self.cleaned_data.get("phone"),
            field_name="Phone number",
        )

    def clean(self):
        """
        "Other" is not a reason on its own — the customer has to say what
        the actual reason was, otherwise the request goes to the refunds
        queue with nothing to review.
        """
        cleaned_data = super().clean()

        if cleaned_data.get("reason") == "OTHER":
            if not (cleaned_data.get("other_reason") or "").strip():
                self.add_error(
                    "other_reason",
                    "Please tell us the reason for your refund.",
                )

        return cleaned_data

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
                "rows": 3,
                "placeholder": "Tell us what went wrong...",
                # Matches RefundRequestForm.clean(): "Other" is not a
                # reason on its own.
                "data-fv-required-when": "reason:OTHER",
                "minlength": 10,
                "maxlength": 1000,
            }),

            "bank_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "NIC Asia, Global IME...",
                "minlength": 2,
                "maxlength": 120,
            }),

            "account_holder": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Name on the account",
                "minlength": 2,
                "maxlength": 120,
            }),

            "account_number": forms.TextInput(attrs={
                "class": "form-control",
                "inputmode": "numeric",
                "data-fv-digits": "1",
                "minlength": 4,
                "maxlength": 50,
            }),

            "branch": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": 120,
            }),

            "phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "9812345678",
                "inputmode": "numeric",
                "data-fv-phone": "1",
                "maxlength": 20,
            }),
        }
