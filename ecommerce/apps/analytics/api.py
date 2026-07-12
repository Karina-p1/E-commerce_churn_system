from decimal import Decimal

from django.http import JsonResponse
from .models import RevenueSummary,RevenueSnapshot
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncYear,
)
from apps.orders.models import Order, OrderItem

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

    line_total = ExpressionWrapper(
        F("price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )

    # Step 1: gross total per order (sum of price*qty across its items,
    # i.e. revenue BEFORE any coupon discount)
    order_gross = (
        OrderItem.objects
        .filter(order__payment_status="PAID")
        .values("order_id")
        .annotate(gross=Sum(line_total))
    )
    gross_by_order = {row["order_id"]: row["gross"] for row in order_gross}

    # Step 2: what the customer actually paid per order (already net of discount)
    orders = Order.objects.filter(payment_status="PAID").values("id", "total_price")
    paid_total_by_order = {row["id"]: row["total_price"] for row in orders}

    # Step 3: walk items, scale each line by (order.total_price / order.gross)
    items = (
        OrderItem.objects
        .filter(order__payment_status="PAID")
        .select_related("product__category")
        .annotate(line_total=line_total)
    )

    category_revenue = {}

    for item in items:
        order_id = item.order_id
        gross = gross_by_order.get(order_id) or Decimal("0")
        paid_total = paid_total_by_order.get(order_id)

        if gross > 0 and paid_total is not None:
            scale = paid_total / gross
        else:
            scale = Decimal("1")

        actual_line_revenue = item.line_total * scale

        category_name = (
            item.product.category.name
            if item.product and item.product.category
            else "Uncategorized"
        )

        category_revenue[category_name] = (
            category_revenue.get(category_name, Decimal("0")) + actual_line_revenue
        )

    # Step 4: sort descending by revenue
    sorted_items = sorted(category_revenue.items(), key=lambda x: x[1], reverse=True)

    labels = [name for name, _ in sorted_items]
    values = [float(rev) for _, rev in sorted_items]

    return JsonResponse({
        "labels": labels,
        "revenue": values,
    })