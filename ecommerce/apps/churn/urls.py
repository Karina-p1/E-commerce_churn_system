from django.urls import path
from . import views

app_name = 'churn'

urlpatterns = [
    path('dashboard/', views.churn_dashboard, name='dashboard'),
]