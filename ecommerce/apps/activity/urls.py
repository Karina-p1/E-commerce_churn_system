from django.urls import path

from .views import log_click
from . import views

app_name = 'activity'

urlpatterns = [
    path(
        'click/<int:product_id>/',
        log_click,
        name='log_click'
    ),
    path(
        "ping/",
        views.activity_ping,
        name="activity_ping",
    ),
]