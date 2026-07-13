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
from django.db.models import Count
from apps.orders.models import RefundRequest

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




def coupon_summary(request):

    paid_orders = Order.objects.filter(payment_status="PAID")

    total_discount_given = (
        paid_orders.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0")
    )

    orders_with_coupon = paid_orders.exclude(coupon__isnull=True).count()
    total_paid_orders = paid_orders.count()

    top_coupons = (
        paid_orders
        .exclude(coupon__isnull=True)
        .values("coupon__code", "coupon__coupon_type")
        .annotate(
            times_used=Count("id"),
            discount_given=Sum("discount_amount"),
        )
        .order_by("-discount_given")[:10]
    )

    coupon_type_breakdown = (
        paid_orders
        .exclude(coupon__isnull=True)
        .values("coupon__coupon_type")
        .annotate(
            times_used=Count("id"),
            discount_given=Sum("discount_amount"),
        )
        .order_by("-discount_given")
    )

    return JsonResponse({
        "total_discount_given": float(total_discount_given),
        "orders_with_coupon": orders_with_coupon,
        "total_paid_orders": total_paid_orders,
        "coupon_usage_rate": (
            round((orders_with_coupon / total_paid_orders) * 100, 1)
            if total_paid_orders else 0
        ),
        "top_coupons": [
            {
                "code": row["coupon__code"],
                "type": row["coupon__coupon_type"],
                "times_used": row["times_used"],
                "discount_given": float(row["discount_given"] or 0),
            }
            for row in top_coupons
        ],
        "coupon_type_breakdown": [
            {
                "type": row["coupon__coupon_type"],
                "times_used": row["times_used"],
                "discount_given": float(row["discount_given"] or 0),
            }
            for row in coupon_type_breakdown
        ],
    })

def refund_summary(request):

    refunded_orders = Order.objects.filter(refund_status="COMPLETED")

    # Order.refund_status breakdown (all statuses, not just completed)
    refund_status_counts = (
        Order.objects
        .values("refund_status")
        .annotate(count=Count("id"))
    )

    total_refunded_amount = (
        refunded_orders.aggregate(total=Sum("total_price"))["total"] or Decimal("0")
    )

    pending_refund_amount = (
        Order.objects
        .filter(refund_status="PENDING")
        .aggregate(total=Sum("total_price"))["total"] or Decimal("0")
    )

    total_refunded_orders = refunded_orders.count()

    # total individual product units refunded, summed across all
    # OrderItems belonging to refunded orders
    total_products_refunded = (
        OrderItem.objects
        .filter(order__refund_status="COMPLETED")
        .aggregate(total=Sum("quantity"))["total"] or 0
    )

    # RefundRequest is the actual submitted request/ticket queue
    refund_request_counts = (
        RefundRequest.objects
        .values("status")
        .annotate(count=Count("id"))
    )

    refund_reason_breakdown = (
        RefundRequest.objects
        .values("reason")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return JsonResponse({
        "refund_status_breakdown": {
            row["refund_status"]: row["count"] for row in refund_status_counts
        },
        "total_refunded_amount": float(total_refunded_amount),
        "pending_refund_amount": float(pending_refund_amount),
        "total_refunded_orders": total_refunded_orders,
        "total_products_refunded": total_products_refunded,
        "refund_request_status_breakdown": {
            row["status"]: row["count"] for row in refund_request_counts
        },
        "refund_reason_breakdown": [
            {"reason": row["reason"], "count": row["count"]}
            for row in refund_reason_breakdown
        ],
    })
