from django.urls import path
from . import views

app_name = "loyalty"

urlpatterns = [
    path("", views.loyalty_dashboard, name="dashboard"),
    path("rewards/", views.loyalty_rewards, name="rewards"),
    path("tiers/", views.loyalty_tiers, name="tiers"),
]
