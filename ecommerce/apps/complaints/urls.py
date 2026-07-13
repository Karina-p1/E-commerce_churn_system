from django.urls import path
from . import views

app_name = "complaints"

urlpatterns = [

    path(
        "",
        views.complaint_list,
        name="list"
    ),

    path(
        "new/",
        views.complaint_create,
        name="create"
    ),

    path(
        "<int:pk>/",
        views.complaint_detail,
        name="detail"
    ),

    path(
        "<int:pk>/edit/",
        views.complaint_edit,
        name="edit"
    ),

    path(
        "<int:pk>/feedback/",
        views.complaint_feedback,
        name="feedback"
    ),
    path('manage/', views.complaint_list_admin, name='complaint_list'),
    path('manage/<int:pk>/', views.complaint_detail_admin, name='complaint_detail'),
    path('manage/<int:pk>/delete/', views.complaint_delete_confirm, name='complaint_delete_confirm'),
]