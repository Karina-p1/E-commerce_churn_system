from django.contrib import admin
from .models import UserEvent


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'event_type',
        'product',
        'created_at',
    )

    list_filter = (
        'event_type',
        'created_at',
    )

    search_fields = (
        'user__username',
        'product__name',
    )

    ordering = (
        '-created_at',
    )