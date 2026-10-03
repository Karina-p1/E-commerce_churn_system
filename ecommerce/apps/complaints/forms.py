from django import forms
from django.core.exceptions import ValidationError

from ecommerce.validators import (
    validate_image,
    validate_text,
)

from .models import Complaint
from apps.orders.models import Order

class OrderChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, order):
        return order.items_summary

class ComplaintForm(forms.ModelForm):

    order = OrderChoiceField(
        queryset=Order.objects.none(),
        # Complaint.order is null=True/blank=True on the model, and a general
        # website complaint has no order to attach to. Declaring the field on
        # the form drops the model's `blank`, so restate `required=False`.
        required=False,
        empty_label="No order / general complaint",
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

    def clean_subject(self):
        return validate_text(
            self.cleaned_data.get("subject"),
            "Subject",
            min_length=5,
            max_length=255,
        )

    def clean_description(self):
        return validate_text(
            self.cleaned_data.get("description"),
            "Description",
            min_length=20,
            max_length=5000,
        )

    def clean_image(self):
        image = self.cleaned_data.get("image")

        if image:
            validate_image(image, field_name="Image")

        return image

    def clean(self):
        """
        A complaint whose description just repeats the subject gives support
        nothing to act on, so catch that before it reaches the queue.
        """
        cleaned_data = super().clean()

        subject = (cleaned_data.get("subject") or "").lower()
        description = (cleaned_data.get("description") or "").lower()

        if subject and description and description == subject:
            self.add_error(
                "description",
                "Please describe the problem in more detail than the "
                "subject.",
            )

        return cleaned_data

    class Meta:

        model = Complaint

        fields = [
            "order",
            "complaint_type",
            "subject",
            "description",
            "image",
        ]

        widgets = {

            "order": forms.Select(attrs={
                "class": "form-select"
            }),

            "complaint_type": forms.Select(attrs={
                "class": "form-select"
            }),

            "subject": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Complaint title",
                "minlength": 5,
                "maxlength": 255,
            }),

            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": (
                    "Describe what happened in detail — this is what "
                    "our support team will work from."
                ),
                "minlength": 20,
                "maxlength": 5000,
            }),

            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/jpeg,image/png,image/gif,image/webp",
                "data-fv-max-size": "5",
            }),
        }


class ComplaintFeedbackForm(forms.ModelForm):

    def clean_customer_rating(self):
        rating = self.cleaned_data.get("customer_rating")

        if rating in (None, ""):
            raise ValidationError("Please give a rating.")

        if not (1 <= rating <= 5):
            raise ValidationError("Rating must be between 1 and 5.")

        return rating

    def clean_customer_feedback(self):
        return validate_text(
            self.cleaned_data.get("customer_feedback"),
            "Feedback",
            required=False,
            min_length=10,
            max_length=2000,
        )

    def clean(self):
        """
        An unhappy customer is the one whose explanation matters most, so a
        low score has to come with a comment.
        """
        cleaned_data = super().clean()

        rating = cleaned_data.get("customer_rating")
        feedback = cleaned_data.get("customer_feedback") or ""

        if rating is not None and rating <= 3 and len(feedback) < 10:
            self.add_error(
                "customer_feedback",
                "Please tell us what went wrong (at least 10 characters).",
            )

        return cleaned_data

    class Meta:

        model = Complaint

        fields = [
            "customer_rating",
            "customer_feedback"
        ]

        widgets = {

            "customer_rating": forms.Select(attrs={
                "class": "form-select"
            }),

            "customer_feedback": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": (
                    "What went wrong? The more detail you give, the "
                    "faster we can fix it."
                ),
                # Matches ComplaintFeedbackForm.clean(): a low score has
                # to come with an explanation.
                "data-fv-required-when": "customer_rating:1|2|3",
                "minlength": 10,
                "maxlength": 2000,
            }),
        }
