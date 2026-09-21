from decimal import Decimal

from django.http import JsonResponse
from django.conf import settings
from .models import RevenueSummary,RevenueSnapshot
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncYear,
)
from apps.orders.models import Order, OrderItem
from django.db.models import Count,Sum
from apps.orders.models import RefundRequest
from django.utils import timezone
def dashboard_summary(request):

    summary = RevenueSummary.objects.first()

    # Today's revenue from the snapshot table (0 if there is no data for today)
    today = timezone.localdate()
    today_revenue = (
        RevenueSnapshot.objects
        .filter(date=today)
        .aggregate(total=Sum("total_revenue"))["total"]
    ) or 0

    data = {
        "total_revenue": float(summary.total_revenue) if summary else 0,
        "total_orders": summary.total_orders if summary else 0,
        "average_order_value": float(summary.average_order_value) if summary else 0,
        "esewa_revenue": float(summary.esewa_revenue) if summary else 0,
        "cod_revenue": float(summary.cod_revenue) if summary else 0,
        "today_revenue": float(today_revenue),
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

def category_sales(request):
    rows = list(
        OrderItem.objects
        .filter(order__payment_status="PAID")
        .values("product_id", "product__category__name", "product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")
    )

    # Load the products so we can ask each one for its Cloudinary link
    Product = OrderItem._meta.get_field("product").related_model
    product_map = Product.objects.in_bulk({r["product_id"] for r in rows})

    products = {}
    for r in rows:
        category = r["product__category__name"] or "Uncategorized"

        image_url = ""
        product = product_map.get(r["product_id"])
        if product and product.image:
            try:
                image_url = product.image.url
            except Exception:
                image_url = ""

        products.setdefault(category, []).append({
            "name": r["product__name"],
            "quantity": r["qty"] or 0,
            "image": image_url,
        })

    totals = sorted(
        ((cat, sum(p["quantity"] for p in items)) for cat, items in products.items()),
        key=lambda x: x[1],
        reverse=True,
    )

    return JsonResponse({
        "labels": [t[0] for t in totals],
        "quantities": [t[1] for t in totals],
        "products": products,
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
