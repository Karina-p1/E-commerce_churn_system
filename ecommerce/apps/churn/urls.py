from django.urls import path
from . import views

app_name = 'churn'

urlpatterns = [
    path('dashboard/', views.churn_dashboard, name='dashboard'),
    path('dashboard/customer/<int:customer_id>/', views.churn_customer_detail, name='customer_detail'),
    path('dashboard/export/high-risk/', views.export_high_risk_csv, name='export_high_risk_csv'),
]