from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_home, name="admin_dashboard"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("profile/", views.admin_profile, name="admin_profile"),

]