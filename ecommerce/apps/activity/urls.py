from django.urls import path

from .views import log_click


urlpatterns=[

    path(
        'click/<int:product_id>/',
        log_click
    )
]