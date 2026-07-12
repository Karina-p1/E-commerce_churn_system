from django.contrib import admin
from django.utils import timezone

from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "complaint_type",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "complaint_type",
    )

    search_fields = (
        "subject",
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "created_at",
    )

    fieldsets = (

        ("Customer", {
            "fields": (
                "user",
                "order",
            )
        }),

        ("Complaint", {
            "fields": (
                "complaint_type",
                "subject",
                "description",
                "image",
            )
        }),

        ("Support", {
            "fields": (
                "status",
                "admin_reply",
            )
        }),

    )

    def save_model(self, request, obj, form, change):

        if obj.status == "RESOLVED" and not obj.resolved_at:
            obj.resolved_at = timezone.now()

        super().save_model(
            request,
            obj,
            form,
            change
        )