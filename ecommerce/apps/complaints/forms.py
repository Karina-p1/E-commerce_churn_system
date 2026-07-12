from django import forms

from .models import Complaint


class ComplaintForm(forms.ModelForm):

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
                "placeholder": "Complaint title"
            }),

            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5
            }),

            "image": forms.ClearableFileInput(attrs={
                "class": "form-control"
            }),
        }


class ComplaintFeedbackForm(forms.ModelForm):

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
                "rows": 4
            }),
        }