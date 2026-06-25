from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm, LoginForm, ProfileUpdateForm


def register_view(request):
    """
    User registration.
    After registration, user is logged in automatically.
    Registration timestamp = customer lifetime start for churn calculation.
    """
    if request.user.is_authenticated:
        return redirect('products:view_products')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                f"Welcome {user.username}! Account created successfully."
            )
            return redirect('products:view_products')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('admin_dashboard')
        return redirect('products:view_products')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")

            # Staff → admin dashboard, regular users → home
            if user.is_staff:
                return redirect('admin_dashboard')
            
            next_url = request.POST.get('next') or request.GET.get('next') or 'products:view_products'
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return render(request, 'accounts/logout.html')

@login_required
def profile_view(request):
    """
    User profile page.
    Shows order history and account details.
    login_required ensures only authenticated users access this.
    """
    return render(request, 'accounts/profile.html', {'user': request.user})


@login_required
def profile_update_view(request):
    """
    Update profile details.
    """
    if request.method == 'POST':
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = ProfileUpdateForm(instance=request.user)

    return render(request, 'accounts/profile_update.html', {'form': form})