from django.shortcuts import render
from django.db.models import Sum, Avg
from .models import  RevenueSnapshot

def analytics_dashboard(request):

    summary = RevenueSnapshot.objects.aggregate(
        total_revenue=Sum("total_revenue"),
        total_orders=Sum("total_orders"),
        average_order_value=Avg("average_order_value"),
    )

    return render(
        request,
        "analytics/dashboard.html",
        {
            "summary": summary
        }
    )
