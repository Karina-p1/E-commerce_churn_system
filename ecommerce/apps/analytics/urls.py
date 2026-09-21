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
        "api/category-sales/",
        api.category_sales,
        name="category_sales",
    ),
    path("api/coupon-summary/", api.coupon_summary, name="coupon-summary"),
    path("api/refund-summary/", api.refund_summary, name="refund-summary"),
    path("api/sync/", api.sync_analytics, name="sync-analytics"),
    path("api/report-pdf/", api.download_report, name="report-pdf"),
]