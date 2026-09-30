from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .forms import RegisterForm, LoginForm, ProfileUpdateForm
from apps.addresses.models import Address


User = get_user_model()


# ============================================================
# SEND EMAIL VERIFICATION
# ============================================================

def send_verification_email(request, user):
    """
    Send an email containing the account verification link.
    """

    uid = urlsafe_base64_encode(
        force_bytes(user.pk)
    )

    token = default_token_generator.make_token(user)

    verification_url = request.build_absolute_uri(
        reverse(
            "verify_email",
            kwargs={
                "uidb64": uid,
                "token": token,
            }
        )
    )

    subject = "Verify your ShopMart account"

    message = f"""
Hello {user.first_name or user.username},

Welcome to ShopMart!

Your account has been created, but you need to verify your email
address before you can log in.

Please click the verification link below:

{verification_url}

After verification, you will be able to log in to your ShopMart account.

If you did not create this account, you can safely ignore this email.

Thank you,
ShopMart Team
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


# ============================================================
# REGISTER
# ============================================================

def register_view(request):
    """
    Register a user and send email verification.

    Newly registered users remain inactive until they verify
    their email address.
    """

    if request.user.is_authenticated:
        return redirect('products:view_products')

    if request.method == 'POST':

        form = RegisterForm(request.POST)

        if form.is_valid():

            # Don't save normally yet because we need to change is_active.
            user = form.save(commit=False)

            # Prevent login until email is verified.
            user.is_active = False

            user.save()

            try:
                send_verification_email(
                    request,
                    user
                )

            except Exception as error:

                # For development so you can see the actual SMTP problem.
                print(
                    "EMAIL VERIFICATION ERROR:",
                    error
                )

                messages.error(
                    request,
                    "Your account was created, but the verification "
                    "email could not be sent. Please contact support "
                    "or try again later."
                )

                return redirect('login')

            messages.success(
                request,
                "Account created successfully! "
                "Please check your email and click the verification "
                "link before logging in."
            )

            return redirect('login')

        else:

            messages.error(
                request,
                "Please fix the errors below."
            )

    else:

        form = RegisterForm()

    return render(
        request,
        'accounts/register.html',
        {
            'form': form
        }
    )


# ============================================================
# VERIFY EMAIL
# ============================================================

def verify_email(request, uidb64, token):
    """
    Activate the user's account after validating the
    verification link.
    """

    try:

        user_id = force_str(
            urlsafe_base64_decode(uidb64)
        )

        user = User.objects.get(
            pk=user_id
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
        User.DoesNotExist
    ):

        user = None

    # Invalid user
    if user is None:

        messages.error(
            request,
            "This verification link is invalid."
        )

        return redirect('login')

    # Already verified
    if user.is_active:

        messages.info(
            request,
            "Your email is already verified. "
            "You can log in."
        )

        return redirect('login')

    # Check verification token
    if default_token_generator.check_token(
        user,
        token
    ):

        user.is_active = True

        user.save(
            update_fields=['is_active']
        )

        messages.success(
            request,
            "Email verified successfully! "
            "You can now log in to your ShopMart account."
        )

        return redirect('login')

    # Invalid/expired token
    messages.error(
        request,
        "This verification link is invalid or has expired."
    )

    return redirect('login')


# ============================================================
# LOGIN
# ============================================================

def login_view(request):

    if request.user.is_authenticated:

        if request.user.is_staff:
            return redirect('analytics_dashboard')

        return redirect('products:view_products')

    if request.method == 'POST':

        form = LoginForm(
            request,
            data=request.POST
        )

        if form.is_valid():

            user = form.get_user()

            login(
                request,
                user
            )

            if user.is_staff:

                return redirect(
                    'analytics_dashboard'
                )

            next_url = (
                request.POST.get('next')
                or request.GET.get('next')
                or 'products:view_products'
            )

            return redirect(next_url)

        else:

            messages.error(
                request,
                "Invalid username/password or your "
                "email has not been verified yet."
            )

    else:

        form = LoginForm()

    return render(
        request,
        'accounts/login.html',
        {
            'form': form
        }
    )


# ============================================================
# LOGOUT
# ============================================================

def logout_view(request):

    logout(request)

    messages.info(
        request,
        "You have been logged out."
    )

    return render(
        request,
        'accounts/logout.html'
    )


# ============================================================
# PROFILE
# ============================================================

@login_required
def profile_view(request):

    default_address = Address.objects.filter(
        user=request.user,
        is_default=True
    ).first()

    return render(
        request,
        "accounts/profile.html",
        {
            "user": request.user,
            "default_address": default_address,
        }
    )


# ============================================================
# PROFILE UPDATE
# ============================================================

@login_required
def profile_update_view(request):

    if request.method == 'POST':

        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Profile updated successfully!"
            )

            return redirect('profile')

        else:

            messages.error(
                request,
                "Please fix the errors below."
            )

    else:

        form = ProfileUpdateForm(
            instance=request.user
        )

    return render(
        request,
        'accounts/profile_update.html',
        {
            'form': form
        }
    )