from django.urls import path
from . import views

urlpatterns = [
    path("profile/", views.admin_profile, name="admin_profile"),

]