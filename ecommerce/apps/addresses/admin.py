from django.contrib import admin
from .models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "label",
        "city",
        "province",
        "is_default",
    )

    list_filter = (
        "province",
        "is_default",
    )

    search_fields = (
        "user__username",
        "city",
        "district",
    )