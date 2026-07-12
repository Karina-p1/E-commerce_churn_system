from django.urls import path
from . import views
from . import api

urlpatterns = [
    path(
        "finance/",
        views.analytics_finance,
        name="analytics_finance",
    ),
    path(
        "dashboard/",
        views.analytics_dashboard,
        name="analytics_dashboard",
    ),
    path(
        "api/dashboard-summary/",
        api.dashboard_summary,
        name="dashboard_summary",
    ),
    path(
        "api/revenue-chart/",
        api.revenue_chart,
        name="revenue_chart",
    ),
    path(
        "api/orders-chart/",
        api.orders_chart_data,
        name="orders_chart_data",
    ),
    path(
        "api/payment-method-chart/",
        api.payment_method_chart,
        name="payment_method_chart",
    ),
    path(
        "api/category-revenue/",
        api.category_revenue_chart,
        name="category_revenue_chart",
    ),
]