from django import forms

from .models import Complaint
from apps.orders.models import Order

class OrderChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, order):
        items = list(order.items.all())

        if not items:
            return f"Order #{order.id}"

        first_item = items[0]
        product_name = first_item.product_name

        if len(items) > 1:
            return f"{product_name} + {len(items) - 1} more"

        return product_name
class ComplaintForm(forms.ModelForm):

    order = OrderChoiceField(
        queryset=Order.objects.none(),
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

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