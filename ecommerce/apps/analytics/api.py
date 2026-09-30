from collections import defaultdict

from datetime import datetime, timedelta

from decimal import Decimal

import io

from xml.sax.saxutils import escape

from django.db.models import Avg, Count, Sum

from django.db.models.functions import TruncDay, TruncMonth, TruncWeek, TruncYear

from django.http import HttpResponse, JsonResponse

from django.utils import timezone

from django.views.decorators.http import require_POST

from reportlab.lib import colors

from reportlab.lib.pagesizes import A4

from reportlab.lib.styles import getSampleStyleSheet

from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.orders.models import Order, OrderItem, RefundRequest

from .models import RevenueSnapshot, RevenueSummary

ZERO = Decimal("0.00")

# -----------------------------------------------------------------------------

# Shared filters / helpers

# -----------------------------------------------------------------------------

def _parse_date(value):

    if not value:

        return None

    try:

        return datetime.strptime(value, "%Y-%m-%d").date()

    except (TypeError, ValueError):

        return None

def _period_dates(request):

    """Return (period, start_date, end_date).

    Supported periods:

    today, daily (last 30 days), weekly (last 12 weeks),

    monthly (last 12 months), yearly (last 5 years), custom.

    """

    today = timezone.localdate()

    period = request.GET.get("period", "today").lower()

    if period == "today":

        return period, today, today

    if period == "daily":

        return period, today - timedelta(days=29), today

    if period == "weekly":

        return period, today - timedelta(days=83), today

    if period == "yearly":

        try:

            start = today.replace(year=today.year - 4, month=1, day=1)

        except ValueError:

            start = today.replace(year=today.year - 4, month=1, day=1)

        return period, start, today

    if period == "custom":

        start = _parse_date(request.GET.get("start")) or today

        end = _parse_date(request.GET.get("end")) or today

        if end < start:

            start, end = end, start

        return period, start, end

    # monthly default: last 12 calendar months including current month

    month_start = today.replace(day=1)

    year = month_start.year

    month = month_start.month - 11

    while month <= 0:

        month += 12

        year -= 1

    return "monthly", month_start.replace(year=year, month=month), today

def _paid_orders(request):

    _, start, end = _period_dates(request)

    return Order.objects.filter(

        payment_status="PAID",

        created_at__date__range=(start, end),

    )

def _refund_orders(request, status=None):

    _, start, end = _period_dates(request)

    qs = Order.objects.filter(created_at__date__range=(start, end))

    if status:

        qs = qs.filter(refund_status=status)

    return qs

def _period_meta(request):

    period, start, end = _period_dates(request)

    return {

        "period": period,

        "start": start.isoformat(),

        "end": end.isoformat(),

    }

def _money(value):

    return float(value or ZERO)

def _order_products_count(order_ids):

    return (

        OrderItem.objects.filter(order_id__in=order_ids)

        .aggregate(total=Sum("quantity"))["total"]

        or 0

    )

def _gross_sales(paid_orders):

    agg = paid_orders.aggregate(

        final=Sum("total_price"),

        coupon=Sum("discount_amount"),

        loyalty=Sum("loyalty_discount_amount"),

    )

    final = agg["final"] or ZERO

    coupon = agg["coupon"] or ZERO

    loyalty = agg["loyalty"] or ZERO

    # total_price is the stored final order total. Reconstruct the amount before

    # discounts so coupon/loyalty deductions are not subtracted twice.

    gross = final + coupon + loyalty

    return gross, final, coupon, loyalty

def _trunc_for_period(period):

    if period == "weekly":

        return TruncWeek("created_at")

    if period == "monthly":

        return TruncMonth("created_at")

    if period == "yearly":

        return TruncYear("created_at")

    return TruncDay("created_at")

def _label_for_bucket(value, period):

    if period == "weekly":

        iso = value.isocalendar()

        return f"Week {iso.week} ({iso.year})"

    if period == "monthly":

        return value.strftime("%b %Y")

    if period == "yearly":

        return value.strftime("%Y")

    return value.strftime("%d %b")

# -----------------------------------------------------------------------------

# Summary cards

# -----------------------------------------------------------------------------

def dashboard_summary(request):

    paid = _paid_orders(request)

    paid_ids = list(paid.values_list("id", flat=True))

    gross, final_revenue, coupon_discount, loyalty_discount = _gross_sales(

        paid)

    order_count = paid.count()

    products_sold = _order_products_count(paid_ids)

    average_order_value = (

        final_revenue / order_count

        if order_count

        else ZERO

    )

    # Refund information is kept for analytics/display only.

    # Do NOT subtract it from revenue again because the Celery

    # revenue workflow already handles completed refunds.

    completed_refunds = _refund_orders(request, "COMPLETED")

    refund_amount = (

        completed_refunds.aggregate(

            total=Sum("total_price")

        )["total"]

        or ZERO

    )

    # Revenue has already been corrected by the refund workflow.

    net_revenue = final_revenue

    data = {

        **_period_meta(request),

        # Financial

        "gross_sales": _money(gross),

        "total_revenue": _money(final_revenue),

        "net_revenue": _money(net_revenue),

        # Sales

        "total_orders": order_count,

        "products_sold": products_sold,

        "average_order_value": _money(average_order_value),

        # Discounts

        "coupon_discount": _money(coupon_discount),

        "loyalty_discount": _money(loyalty_discount),

        "total_discounts": _money(

            coupon_discount + loyalty_discount

        ),

        # Refund analytics only — NOT deducted again

        "refund_amount": _money(refund_amount),

    }

    return JsonResponse(data)

# -----------------------------------------------------------------------------

# Combined sales performance: revenue + orders + products sold + AOV

# -----------------------------------------------------------------------------

def sales_performance(request):

    period, _, _ = _period_dates(request)

    paid = _paid_orders(request)

    trunc = _trunc_for_period(period)

    order_rows = list(

        paid.annotate(bucket=trunc)

        .values("bucket")

        .annotate(

            revenue=Sum("total_price"),

            orders=Count("id"),

        )

        .order_by("bucket")

    )

    # Product quantities must be grouped by the related Order date.

    if period == "weekly":

        item_trunc = TruncWeek("order__created_at")

    elif period == "monthly":

        item_trunc = TruncMonth("order__created_at")

    elif period == "yearly":

        item_trunc = TruncYear("order__created_at")

    else:

        item_trunc = TruncDay("order__created_at")

    item_rows = (

        OrderItem.objects.filter(order__in=paid)

        .annotate(bucket=item_trunc)

        .values("bucket")

        .annotate(products_sold=Sum("quantity"))

        .order_by("bucket")

    )

    products_by_bucket = {

        row["bucket"]: row["products_sold"] or 0 for row in item_rows

    }

    points = []

    for row in order_rows:

        revenue = row["revenue"] or ZERO

        orders = row["orders"] or 0

        products = products_by_bucket.get(row["bucket"], 0)

        points.append({

            "label": _label_for_bucket(row["bucket"], period),

            "revenue": _money(revenue),

            "orders": orders,

            "products_sold": products,

            "average_order_value": _money(revenue / orders if orders else ZERO),

        })

    return JsonResponse({

        **_period_meta(request),

        "points": points,

        "labels": [p["label"] for p in points],

        "revenue": [p["revenue"] for p in points],

        "orders": [p["orders"] for p in points],

        "products_sold": [p["products_sold"] for p in points],

        "average_order_value": [p["average_order_value"] for p in points],

    })

# -----------------------------------------------------------------------------

# Backward-compatible chart endpoints

# -----------------------------------------------------------------------------

def revenue_chart(request):

    period, start, end = _period_dates(request)

    snapshots = RevenueSnapshot.objects.filter(date__range=(start, end))

    if period == "weekly":

        rows = snapshots.annotate(bucket=TruncWeek("date")).values("bucket").annotate(

            revenue=Sum("total_revenue")

        ).order_by("bucket")

    elif period == "monthly":

        rows = snapshots.annotate(bucket=TruncMonth("date")).values("bucket").annotate(

            revenue=Sum("total_revenue")

        ).order_by("bucket")

    elif period == "yearly":

        rows = snapshots.annotate(bucket=TruncYear("date")).values("bucket").annotate(

            revenue=Sum("total_revenue")

        ).order_by("bucket")

    else:

        rows = snapshots.annotate(bucket=TruncDay("date")).values("bucket").annotate(

            revenue=Sum("total_revenue")

        ).order_by("bucket")

    labels = [_label_for_bucket(r["bucket"], period) for r in rows]

    values = [_money(r["revenue"]) for r in rows]

    return JsonResponse({"labels": labels, "revenue": values})

def orders_chart_data(request):

    period, start, end = _period_dates(request)

    snapshots = RevenueSnapshot.objects.filter(date__range=(start, end))

    if period == "weekly":

        rows = snapshots.annotate(bucket=TruncWeek("date")).values("bucket").annotate(

            orders=Sum("total_orders")

        ).order_by("bucket")

    elif period == "monthly":

        rows = snapshots.annotate(bucket=TruncMonth("date")).values("bucket").annotate(

            orders=Sum("total_orders")

        ).order_by("bucket")

    elif period == "yearly":

        rows = snapshots.annotate(bucket=TruncYear("date")).values("bucket").annotate(

            orders=Sum("total_orders")

        ).order_by("bucket")

    else:

        rows = snapshots.annotate(bucket=TruncDay("date")).values("bucket").annotate(

            orders=Sum("total_orders")

        ).order_by("bucket")

    labels = [_label_for_bucket(r["bucket"], period) for r in rows]

    values = [r["orders"] or 0 for r in rows]

    return JsonResponse({"labels": labels, "orders": values})

# -----------------------------------------------------------------------------

# Payment method analysis

# -----------------------------------------------------------------------------

def payment_method_chart(request):

    paid = _paid_orders(request)

    rows = (

        paid.values("payment_method")

        .annotate(revenue=Sum("total_price"), orders=Count("id"))

        .order_by("payment_method")

    )

    labels = []

    values = []

    orders = []

    for row in rows:

        method = (row["payment_method"] or "Unknown").upper()

        labels.append("eSewa" if method ==

                      "ESEWA" else "Cash On Delivery" if method == "COD" else method)

        values.append(_money(row["revenue"]))

        orders.append(row["orders"] or 0)

    return JsonResponse({

        **_period_meta(request),

        "labels": labels,

        "values": values,

        "orders": orders,

    })

# -----------------------------------------------------------------------------

# Category + product performance

# -----------------------------------------------------------------------------

def category_sales(request):

    paid = _paid_orders(request)

    completed_refunds = _refund_orders(request, "COMPLETED")

    sold_rows = list(

        OrderItem.objects.filter(order__in=paid)

        .values(

            "product_id",

            "product__category__name",

            "product__name",

        )

        .annotate(

            quantity=Sum("quantity"),

            sales=Sum("order__total_price"),

        )

    )

    refunded_qty = {

        row["product_id"]: row["qty"] or 0

        for row in (

            OrderItem.objects.filter(order__in=completed_refunds)

            .values("product_id")

            .annotate(qty=Sum("quantity"))

        )

    }

    Product = OrderItem._meta.get_field("product").related_model

    product_ids = {r["product_id"] for r in sold_rows if r["product_id"]}

    product_map = Product.objects.in_bulk(product_ids)

    categories = defaultdict(lambda: {

        "quantity": 0,

        "revenue": ZERO,

        "refund_quantity": 0,

        "products": [],

    })

    # Use item historical price for product/category revenue so each item is

    # counted once. Coupon discount is reported separately in finance/coupon APIs.

    item_financial_rows = (

        OrderItem.objects.filter(order__in=paid)

        .values("product_id", "product__category__name", "product__name", "price")

        .annotate(quantity=Sum("quantity"))

    )

    for row in item_financial_rows:

        category = row["product__category__name"] or "Uncategorized"

        qty = row["quantity"] or 0

        revenue = (row["price"] or ZERO) * qty

        refund_qty = refunded_qty.get(row["product_id"], 0)

        product = product_map.get(row["product_id"])

        image_url = ""

        if product and getattr(product, "image", None):

            try:

                image_url = product.image.url

            except Exception:

                image_url = ""

        categories[category]["quantity"] += qty

        categories[category]["revenue"] += revenue

        categories[category]["refund_quantity"] += refund_qty

        categories[category]["products"].append({

            "id": row["product_id"],

            "name": row["product__name"],

            "quantity": qty,

            "revenue": _money(revenue),

            "refunded_quantity": refund_qty,

            "image": image_url,

        })

    ordered = sorted(categories.items(),

                     key=lambda x: x[1]["revenue"], reverse=True)

    return JsonResponse({

        **_period_meta(request),

        "labels": [name for name, _ in ordered],

        "quantities": [data["quantity"] for _, data in ordered],

        "revenues": [_money(data["revenue"]) for _, data in ordered],

        "refund_quantities": [data["refund_quantity"] for _, data in ordered],

        "products": {name: data["products"] for name, data in ordered},

        "categories": [

            {

                "name": name,

                "quantity": data["quantity"],

                "revenue": _money(data["revenue"]),

                "refunded_quantity": data["refund_quantity"],

            }

            for name, data in ordered

        ],

    })

# -----------------------------------------------------------------------------

# Coupon performance

# -----------------------------------------------------------------------------

def coupon_summary(request):

    paid = _paid_orders(request)

    total_paid_orders = paid.count()

    coupon_orders = paid.exclude(coupon__isnull=True)

    orders_with_coupon = coupon_orders.count()

    total_discount = paid.aggregate(total=Sum("discount_amount"))[

        "total"] or ZERO

    top = (

        coupon_orders.values("coupon__code", "coupon__coupon_type")

        .annotate(

            times_used=Count("id"),

            revenue_generated=Sum("total_price"),

            discount_given=Sum("discount_amount"),

            average_order_value=Avg("total_price"),

        )

        .order_by("-revenue_generated")[:20]

    )

    type_breakdown = (

        coupon_orders.values("coupon__coupon_type")

        .annotate(

            times_used=Count("id"),

            revenue_generated=Sum("total_price"),

            discount_given=Sum("discount_amount"),

        )

        .order_by("-revenue_generated")

    )

    return JsonResponse({

        **_period_meta(request),

        "total_discount_given": _money(total_discount),

        "orders_with_coupon": orders_with_coupon,

        "total_paid_orders": total_paid_orders,

        "coupon_usage_rate": round((orders_with_coupon / total_paid_orders) * 100, 1) if total_paid_orders else 0,

        "top_coupons": [

            {

                "code": row["coupon__code"],

                "type": row["coupon__coupon_type"],

                "times_used": row["times_used"],

                "orders": row["times_used"],

                "revenue_generated": _money(row["revenue_generated"]),

                "discount_given": _money(row["discount_given"]),

                "average_order_value": _money(row["average_order_value"]),

            }

            for row in top

        ],

        "coupon_type_breakdown": [

            {

                "type": row["coupon__coupon_type"],

                "times_used": row["times_used"],

                "revenue_generated": _money(row["revenue_generated"]),

                "discount_given": _money(row["discount_given"]),

            }

            for row in type_breakdown

        ],

    })

# -----------------------------------------------------------------------------

# Refund analysis

# -----------------------------------------------------------------------------

def refund_summary(request):

    _, start, end = _period_dates(request)

    period_orders = Order.objects.filter(

        created_at__date__range=(start, end)

    )

    completed = period_orders.filter(refund_status="COMPLETED")

    paid = period_orders.filter(payment_status="PAID")


    completed_amount = (

        completed.aggregate(total=Sum("total_price"))["total"]

        or ZERO

    )


    refunded_order_count = completed.count()

    paid_order_count = paid.count()

    # ---------------------------------------------------------

    # TOTAL REFUNDED PRODUCT UNITS

    # ---------------------------------------------------------

    refunded_items = (

        OrderItem.objects.filter(order__in=completed)

        .values("product_id", "product_name")

        .annotate(quantity=Sum("quantity"))

        .order_by("-quantity")

    )

    total_products_refunded = sum(

        row["quantity"] or 0

        for row in refunded_items

    )

    # ---------------------------------------------------------

    # REFUND REASON PER ORDER

    # ---------------------------------------------------------

    # RefundRequest is order-level, therefore all products

    # belonging to that refunded order share the same reason.

    reason_by_order = {

        r["order_id"]: r["reason"]

        for r in RefundRequest.objects.filter(

            order__created_at__date__range=(start, end),

            status="COMPLETED",

        ).values("order_id", "reason")

    }

    # ---------------------------------------------------------

    # COMPLETED REFUNDED ORDERS

    # ---------------------------------------------------------

    # We need the order-level coupon and loyalty discounts

    # because they must be distributed across the products.

    completed_orders_data = {

        row["id"]: {

            "discount_amount": row["discount_amount"] or ZERO,

            "loyalty_discount_amount": (

                row["loyalty_discount_amount"] or ZERO

            ),

        }

        for row in completed.values(

            "id",

            "discount_amount",

            "loyalty_discount_amount",

        )

    }

    # ---------------------------------------------------------

    # GET ITEMS FROM COMPLETED REFUNDED ORDERS

    # ---------------------------------------------------------

    completed_item_rows = list(

        OrderItem.objects.filter(

            order__in=completed

        ).values(

            "order_id",

            "product_id",

            "product_name",

            "price",

            "quantity",

        )

    )

    # ---------------------------------------------------------

    # CALCULATE PRODUCT SUBTOTAL FOR EACH ORDER

    # ---------------------------------------------------------

    #

    # Example:

    #

    # Product A = Rs. 4,000

    # Product B = Rs. 6,000

    #

    # Order product subtotal = Rs. 10,000

    #

    # This lets us determine what percentage of the order

    # belongs to each product.

    # ---------------------------------------------------------

    order_product_subtotals = defaultdict(lambda: ZERO)

    for row in completed_item_rows:

        item_total = (

            (row["price"] or ZERO)

            * (row["quantity"] or 0)

        )

        order_product_subtotals[row["order_id"]] += item_total

    # ---------------------------------------------------------

    # PRODUCT REFUND STATISTICS

    # ---------------------------------------------------------

    product_reason_counts = defaultdict(

        lambda: defaultdict(int)

    )

    product_stats = defaultdict(

        lambda: {

            "product_id": None,

            "product_name": "",

            "quantity": 0,

            # This now means:

            # amount actually paid by customer after

            # coupon + loyalty discounts.

            "refund_amount": ZERO,

        }

    )

    for row in completed_item_rows:

        order_id = row["order_id"]

        quantity = row["quantity"] or 0

        price = row["price"] or ZERO

        original_item_total = price * quantity

        # Total value of products in this order

        order_subtotal = order_product_subtotals[order_id]

        # Get the discounts belonging to this order

        order_data = completed_orders_data.get(

            order_id,

            {}

        )

        coupon_discount = (

            order_data.get("discount_amount", ZERO)

            or ZERO

        )

        loyalty_discount = (

            order_data.get(

                "loyalty_discount_amount",

                ZERO

            )

            or ZERO

        )

        total_discount = (

            coupon_discount

            + loyalty_discount

        )

        # -----------------------------------------------------

        # DISTRIBUTE DISCOUNT PROPORTIONALLY

        # -----------------------------------------------------

        if order_subtotal > ZERO:

            item_ratio = (

                original_item_total

                / order_subtotal

            )

            item_discount_share = (

                total_discount

                * item_ratio

            )

        else:

            item_discount_share = ZERO

        # -----------------------------------------------------

        # ACTUAL AMOUNT PAID FOR THIS PRODUCT

        # -----------------------------------------------------

        amount_paid = max(

            original_item_total

            - item_discount_share,

            ZERO

        )

        # -----------------------------------------------------

        # GROUP SAME PRODUCTS TOGETHER

        # -----------------------------------------------------

        key = (

            row["product_id"]

            or row["product_name"]

        )

        stat = product_stats[key]

        stat["product_id"] = row["product_id"]

        stat["product_name"] = row["product_name"]

        stat["quantity"] += quantity

        # IMPORTANT:

        # Store discounted amount instead of original amount.

        stat["refund_amount"] += amount_paid

        # -----------------------------------------------------

        # REFUND REASON

        # -----------------------------------------------------

        reason = reason_by_order.get(

            order_id,

            "OTHER"

        )

        product_reason_counts[key][reason] += quantity

    # ---------------------------------------------------------

    # BUILD MOST REFUNDED PRODUCTS RESPONSE

    # ---------------------------------------------------------

    most_refunded = []

    for key, stat in product_stats.items():

        reasons = product_reason_counts[key]

        main_reason = (

            max(reasons, key=reasons.get)

            if reasons

            else "OTHER"

        )

        most_refunded.append({

            "product_id": stat["product_id"],

            "product_name": stat["product_name"],

            "quantity": stat["quantity"],

            # This is now what the customer actually paid

            # after coupon + loyalty discount.

            "refund_amount": _money(

                stat["refund_amount"]

            ),

            "main_reason": main_reason,

        })

    # Most refunded quantity first

    most_refunded.sort(

        key=lambda x: x["quantity"],

        reverse=True

    )

    # ---------------------------------------------------------

    # REFUND STATUS BREAKDOWN

    # ---------------------------------------------------------

    status_counts = (

        period_orders

        .values("refund_status")

        .annotate(count=Count("id"))

    )

    request_status_counts = (

        RefundRequest.objects.filter(

            order__created_at__date__range=(start, end)

        )

        .values("status")

        .annotate(count=Count("id"))

    )

    # ---------------------------------------------------------

    # REFUND REASON BREAKDOWN

    # ---------------------------------------------------------

    reason_breakdown = (

        RefundRequest.objects.filter(

            order__created_at__date__range=(start, end)

        )

        .values("reason")

        .annotate(count=Count("id"))

        .order_by("-count")

    )

    # ---------------------------------------------------------

    # RESPONSE

    # ---------------------------------------------------------

    return JsonResponse({

        **_period_meta(request),

        "total_refunded_amount": _money(

            completed_amount

        ),


        "total_refunded_orders": refunded_order_count,

        "total_products_refunded": (

            total_products_refunded

        ),

        "refund_rate": round(

            (

                refunded_order_count

                / paid_order_count

            ) * 100,

            1

        ) if paid_order_count else 0,

        "refund_status_breakdown": {

            r["refund_status"]: r["count"]

            for r in status_counts

        },

        "refund_request_status_breakdown": {

            r["status"]: r["count"]

            for r in request_status_counts

        },

        "refund_reason_breakdown": [

            {

                "reason": r["reason"],

                "count": r["count"],

            }

            for r in reason_breakdown

        ],

        "most_refunded_products": (

            most_refunded[:15]

        ),

    })

# -----------------------------------------------------------------------------

# Sync snapshots + all-time summary

# -----------------------------------------------------------------------------

@require_POST

def sync_analytics(request):

    paid = Order.objects.filter(payment_status="PAID")

    daily = list(

        paid.annotate(day=TruncDay("created_at"))

        .values("day")

        .annotate(

            revenue=Sum("total_price"),

            orders=Count("id"),

        )

        .order_by("day")

    )

    for row in daily:

        day = row["day"].date() if hasattr(row["day"], "date") else row["day"]

        revenue = row["revenue"] or ZERO

        orders = row["orders"] or 0

        day_orders = paid.filter(created_at__date=day)

        esewa = day_orders.filter(payment_method__iexact="esewa").aggregate(

            t=Sum("total_price"))["t"] or ZERO

        cod = day_orders.filter(payment_method__iexact="cod").aggregate(

            t=Sum("total_price"))["t"] or ZERO

        RevenueSnapshot.objects.update_or_create(

            date=day,

            defaults={

                "total_revenue": revenue,

                "total_orders": orders,

                "average_order_value": revenue / orders if orders else ZERO,

                "esewa_revenue": esewa,

                "cod_revenue": cod,

            },

        )

    total = paid.aggregate(t=Sum("total_price"))["t"] or ZERO

    orders = paid.count()

    esewa = paid.filter(payment_method__iexact="esewa").aggregate(

        t=Sum("total_price"))["t"] or ZERO

    cod = paid.filter(payment_method__iexact="cod").aggregate(

        t=Sum("total_price"))["t"] or ZERO

    summary = RevenueSummary.objects.first() or RevenueSummary()

    summary.total_revenue = total

    summary.total_orders = orders

    summary.average_order_value = total / orders if orders else ZERO

    summary.esewa_revenue = esewa

    summary.cod_revenue = cod

    summary.save()

    return JsonResponse({"ok": True, "days_synced": len(daily)})

# -----------------------------------------------------------------------------

# PDF report

# -----------------------------------------------------------------------------

def _table(data, col_widths=None, header=True):

    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)

    style = [

        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),

        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("FONTSIZE", (0, 0), (-1, -1), 8),

    ]

    if header:

        style += [

            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#198754")),

            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

        ]

    table.setStyle(TableStyle(style))

    return table

def download_report(request):

    styles = getSampleStyleSheet()

    story = []

    def money(value): return f"Rs. {float(value or 0):,.2f}"

    period, start, end = _period_dates(request)

    paid = _paid_orders(request)

    paid_ids = list(paid.values_list("id", flat=True))

    gross, revenue, coupon_discount, loyalty_discount = _gross_sales(paid)

    completed_refunds = _refund_orders(request, "COMPLETED")

    refund_amount = completed_refunds.aggregate(

        t=Sum("total_price"))["t"] or ZERO

    net = revenue

    order_count = paid.count()

    products_sold = _order_products_count(paid_ids)

    aov = revenue / order_count if order_count else ZERO

    story.append(

        Paragraph("Financial & Sales Analytics Report", styles["Title"]))

    story.append(Paragraph(

        f"Period: {start:%d %b %Y} - {end:%d %b %Y} ({period.title()})",

        styles["Normal"],

    ))

    story.append(Paragraph(

        f"Generated: {timezone.localtime():%d %b %Y, %I:%M %p}",

        styles["Normal"],

    ))

    story.append(Spacer(1, 14))

    story.append(Paragraph("1. Financial Summary", styles["Heading2"]))

    story.append(_table([

        ["Measure", "Value"],

        ["Gross sales before discounts", money(gross)],

        ["Paid revenue", money(revenue)],

        ["Orders", str(order_count)],

        ["Products sold", str(products_sold)],

        ["Average order value", money(aov)],

        ["Coupon discounts", money(coupon_discount)],

        ["Loyalty discounts", money(loyalty_discount)],

        ["Completed refunds", money(refund_amount)],

    ], col_widths=[260, 190]))

    story.append(Spacer(1, 14))

    story.append(Paragraph("2. Coupon Performance", styles["Heading2"]))

    coupon_rows = [["Coupon", "Type", "Uses", "Revenue", "Discount", "AOV"]]

    coupons = (

        paid.exclude(coupon__isnull=True)

        .values("coupon__code", "coupon__coupon_type")

        .annotate(

            uses=Count("id"),

            revenue=Sum("total_price"),

            discount=Sum("discount_amount"),

            aov=Avg("total_price"),

        )

        .order_by("-revenue")[:15]

    )

    for row in coupons:

        coupon_rows.append([

            Paragraph(escape(str(row["coupon__code"])), styles["Normal"]),

            row["coupon__coupon_type"],

            str(row["uses"]),

            money(row["revenue"]),

            money(row["discount"]),

            money(row["aov"]),

        ])

    if len(coupon_rows) == 1:

        coupon_rows.append(["No coupon usage", "-", "-", "-", "-", "-"])

    story.append(_table(coupon_rows, col_widths=[75, 75, 40, 90, 90, 80]))

    story.append(Spacer(1, 14))

    story.append(Paragraph("3. Refund Analysis", styles["Heading2"]))

    refunded_units = OrderItem.objects.filter(

        order__in=completed_refunds).aggregate(t=Sum("quantity"))["t"] or 0

    story.append(_table([

        ["Measure", "Value"],

        ["Completed refund amount", money(refund_amount)],


        ["Refunded orders", str(completed_refunds.count())],

        ["Refunded product units", str(refunded_units)],

    ], col_widths=[260, 190]))

    story.append(Spacer(1, 14))

    story.append(Paragraph("4. Product Sales", styles["Heading2"]))

    product_rows = [["Product", "Qty Sold", "Sales"]]

    products = (

        OrderItem.objects.filter(order__in=paid)

        .values("product_name", "price")

        .annotate(qty=Sum("quantity"))

        .order_by("-qty")[:30]

    )

    for row in products:

        product_rows.append([

            Paragraph(escape(str(row["product_name"])), styles["Normal"]),

            str(row["qty"] or 0),

            money((row["price"] or ZERO) * (row["qty"] or 0)),

        ])

    if len(product_rows) == 1:

        product_rows.append(["No sales", "-", "-"])

    story.append(_table(product_rows, col_widths=[250, 80, 120]))

    buffer = io.BytesIO()

    SimpleDocTemplate(

        buffer,

        pagesize=A4,

        title="Financial & Sales Analytics Report",

    ).build(story)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")

    response["Content-Disposition"] = (

        f'attachment; filename="analytics-report-{start}-{end}.pdf"'

    )

    return response
