from django.urls import path

from .views import log_click


app_name = 'activity'

urlpatterns = [
    path(
        'click/<int:product_id>/',
        log_click,
        name='log_click'
    ),
]