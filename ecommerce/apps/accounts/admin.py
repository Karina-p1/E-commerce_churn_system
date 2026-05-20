from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        'username', 'email', 'first_name',
        'last_name', 'is_staff', 'created_at'
    ]
    list_filter = ['is_staff', 'is_active', 'created_at']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    # Add our custom fields to the admin form
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Info', {
            'fields': ('phone_number', 'profile_image')
        }),
    )