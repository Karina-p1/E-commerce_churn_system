from django.contrib import admin
from .models import UserEvent
from apps.activity.models import UserSession

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

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "started_at",
        "active_time",
        "last_activity",
        "ended_at",
    )