from django.http import JsonResponse
from .models import RevenueSummary,RevenueSnapshot
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncYear,
)
from apps.orders.models import OrderItem

def dashboard_summary(request):

    summary = RevenueSummary.objects.first()

    data = {

        "total_revenue": float(summary.total_revenue),

        "total_orders": summary.total_orders,

        "average_order_value": float(
            summary.average_order_value
        ),

        "esewa_revenue": float(summary.esewa_revenue),

        "cod_revenue": float(summary.cod_revenue),

    }

    return JsonResponse(data)

def payment_method_chart(request):

    summary = RevenueSummary.objects.first()

    if not summary:
        return JsonResponse({
            "labels": [],
            "values": [],
        })

    return JsonResponse({
        "labels": ["eSewa", "Cash On Delivery"],
        "values": [
            float(summary.esewa_revenue),
            float(summary.cod_revenue),
        ]
    })

# ---------------------------------------
# Revenue Chart (fixed to properly aggregate)
# ---------------------------------------

def revenue_chart(request):

    period = request.GET.get("period", "daily")

    base_qs = RevenueSnapshot.objects.all()

    if period == "weekly":

        rows = (
            base_qs
            .annotate(period=TruncWeek("date"))
            .values("period")
            .annotate(revenue=Sum("total_revenue"))
            .order_by("period")
        )

        labels = [
            f"Week {row['period'].isocalendar().week} ({row['period'].year})"
            for row in rows
        ]
        revenue = [float(row["revenue"]) for row in rows]

    elif period == "monthly":

        rows = (
            base_qs
            .annotate(period=TruncMonth("date"))
            .values("period")
            .annotate(revenue=Sum("total_revenue"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%b %Y") for row in rows]
        revenue = [float(row["revenue"]) for row in rows]

    elif period == "yearly":

        rows = (
            base_qs
            .annotate(period=TruncYear("date"))
            .values("period")
            .annotate(revenue=Sum("total_revenue"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%Y") for row in rows]
        revenue = [float(row["revenue"]) for row in rows]

    else:  # daily

        rows = (
            base_qs
            .annotate(period=TruncDay("date"))
            .values("period")
            .annotate(revenue=Sum("total_revenue"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%d %b") for row in rows]
        revenue = [float(row["revenue"]) for row in rows]

    return JsonResponse({
        "labels": labels,
        "revenue": revenue,
    })


# ---------------------------------------
# Orders Chart (unchanged - already working)
# ---------------------------------------

def orders_chart_data(request):

    period = request.GET.get("period", "daily")

    snapshots = RevenueSnapshot.objects.all()

    if period == "weekly":

        snapshots = (
            snapshots
            .annotate(period=TruncWeek("date"))
            .values("period")
            .annotate(orders=Sum("total_orders"))
            .order_by("period")
        )

        labels = [
            f"Week {row['period'].isocalendar().week} ({row['period'].year})"
            for row in snapshots
        ]
        orders = [row["orders"] for row in snapshots]

    elif period == "monthly":

        snapshots = (
            snapshots
            .annotate(period=TruncMonth("date"))
            .values("period")
            .annotate(orders=Sum("total_orders"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%b %Y") for row in snapshots]
        orders = [row["orders"] for row in snapshots]

    elif period == "yearly":

        snapshots = (
            snapshots
            .annotate(period=TruncYear("date"))
            .values("period")
            .annotate(orders=Sum("total_orders"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%Y") for row in snapshots]
        orders = [row["orders"] for row in snapshots]

    else:

        snapshots = (
            snapshots
            .annotate(period=TruncDay("date"))
            .values("period")
            .annotate(orders=Sum("total_orders"))
            .order_by("period")
        )

        labels = [row["period"].strftime("%d %b") for row in snapshots]
        orders = [row["orders"] for row in snapshots]

    return JsonResponse({
        "labels": labels,
        "orders": orders,
    })

def category_revenue_chart(request):

    revenue = ExpressionWrapper(
        F("price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    qs = (
        OrderItem.objects
        .filter(order__payment_status="PAID")
        .values("product__category__name")
        .annotate(
            revenue=Sum(revenue)
        )
        .order_by("-revenue")
    )

    labels = []
    values = []

    for row in qs:

        labels.append(
            row["product__category__name"] or "Uncategorized"
        )

        values.append(float(row["revenue"]))

    return JsonResponse({
        "labels": labels,
        "revenue": values,
    })