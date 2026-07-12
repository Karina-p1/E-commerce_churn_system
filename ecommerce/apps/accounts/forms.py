from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User

class RegisterForm(UserCreationForm):
    """
    Registration form.
    Collects email, name, phone, gender, and marital status — all useful
    for churn analysis. Gender and marital status are required so the
    churn model always receives real data instead of a guessed default.
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name'
        })
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name'
        })
    )
    phone_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone number (optional)'
        })
    )
    gender = forms.ChoiceField(
        required=True,
        choices=User.GENDER_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    marital_status = forms.ChoiceField(
        required=True,
        choices=User.MARITAL_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )

    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'phone_number',
            'gender',
            'marital_status',
            'password1',
            'password2'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email


class LoginForm(AuthenticationForm):
    """
    Login form with Bootstrap styling.
    Login events are tracked as activity — critical for churn recency.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Username'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })


class ProfileUpdateForm(forms.ModelForm):
    """
    Profile update form.
    """
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'profile_image',
            'gender',
            'marital_status',
            'email_notifications_enabled',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Checkbox fields shouldn't get the text-input 'form-control' class —
            # give them 'form-check-input' instead so they render correctly.
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = 'form-control'