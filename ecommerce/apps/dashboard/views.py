from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Avg, F
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from apps.products.models import Product, Category, Brand, Wishlist


def get_model_or_none(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def get_first_field(model, possible_fields):
    if not model:
        return None

    model_fields = [field.name for field in model._meta.get_fields()]

    for field in possible_fields:
        if field in model_fields:
            return field

    return None


def get_total_sales(Order):
    if not Order:
        return Decimal("0.00")

    total_field = get_first_field(
        Order,
        [
            "total_amount",
            "total_price",
            "grand_total",
            "final_total",
            "amount",
            "total",
        ],
    )

    if not total_field:
        return Decimal("0.00")

    return Order.objects.aggregate(total=Sum(total_field))["total"] or Decimal("0.00")


def get_recent_orders(Order):
    if not Order:
        return []

    date_field = get_first_field(Order, ["created_at", "order_date", "ordered_at", "date"])

    queryset = Order.objects.all()

    if date_field:
        queryset = queryset.order_by(f"-{date_field}")
    else:
        queryset = queryset.order_by("-id")

    return queryset[:6]


def get_revenue_chart(Order):
    revenue_chart = []

    if not Order:
        return revenue_chart

    date_field = get_first_field(Order, ["created_at", "order_date", "ordered_at", "date"])
    total_field = get_first_field(
        Order,
        [
            "total_amount",
            "total_price",
            "grand_total",
            "final_total",
            "amount",
            "total",
        ],
    )

    if not date_field or not total_field:
        return revenue_chart

    today = timezone.now().date()
    start_date = today - timedelta(days=6)

    data = (
        Order.objects
        .filter(**{f"{date_field}__date__gte": start_date})
        .annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(revenue=Sum(total_field))
        .order_by("day")
    )

    revenue_map = {
        item["day"]: item["revenue"] or 0
        for item in data
    }

    for i in range(7):
        day = start_date + timedelta(days=i)
        revenue_chart.append({
            "label": day.strftime("%b %d"),
            "revenue": float(revenue_map.get(day, 0)),
        })

    return revenue_chart


def get_best_selling_products(OrderItem, UserEvent):
    best_selling_products = []

    if OrderItem:
        product_field = get_first_field(OrderItem, ["product"])
        quantity_field = get_first_field(OrderItem, ["quantity", "qty"])

        if product_field and quantity_field:
            best_selling_products = (
                OrderItem.objects
                .values("product__name")
                .annotate(total_sold=Sum(quantity_field))
                .order_by("-total_sold")[:5]
            )

    if not best_selling_products and UserEvent:
        best_selling_products = (
            UserEvent.objects
            .filter(event_type="ORDER", product__isnull=False)
            .values("product__name")
            .annotate(total_sold=Count("id"))
            .order_by("-total_sold")[:5]
        )

    return best_selling_products


@staff_member_required
def dashboard_home(request):
    User = get_user_model()

    Order = get_model_or_none("orders", "Order")
    OrderItem = get_model_or_none("orders", "OrderItem")
    UserEvent = get_model_or_none("activity", "UserEvent")

    total_sales = get_total_sales(Order)
    total_orders = Order.objects.count() if Order else 0
    total_customers = User.objects.filter(is_staff=False).count()
    total_products = Product.objects.count()

    active_products = Product.objects.filter(is_active=True).count()
    out_of_stock_products = Product.objects.filter(stock=0).count()
    low_stock_products = Product.objects.filter(stock__gt=0, stock__lte=5).count()

    recent_orders = get_recent_orders(Order)
    revenue_chart = get_revenue_chart(Order)
    best_selling_products = get_best_selling_products(OrderItem, UserEvent)

    top_wishlisted_products = (
        Product.objects
        .annotate(wishlist_count=Count("wishlisted_by"))
        .order_by("-wishlist_count")[:5]
    )

    context = {
        "total_sales": total_sales,
        "total_orders": total_orders,
        "total_customers": total_customers,
        "total_products": total_products,
        "active_products": active_products,
        "out_of_stock_products": out_of_stock_products,
        "low_stock_products": low_stock_products,
        "recent_orders": recent_orders,
        "revenue_chart": revenue_chart,
        "best_selling_products": best_selling_products,
        "top_wishlisted_products": top_wishlisted_products,
    }

    return render(request, "dashboard/dashboard.html", context)


@staff_member_required
def analytics_view(request):
    User = get_user_model()

    Order = get_model_or_none("orders", "Order")
    OrderItem = get_model_or_none("orders", "OrderItem")
    UserEvent = get_model_or_none("activity", "UserEvent")

    ChurnScore = (
        get_model_or_none("churn", "ChurnScore")
        or get_model_or_none("churn", "ChurnPrediction")
        or get_model_or_none("churn", "Prediction")
    )

    total_sales = get_total_sales(Order)
    total_orders = Order.objects.count() if Order else 0
    total_customers = User.objects.filter(is_staff=False).count()

    product_views = 0
    cart_activity = 0
    wishlist_activity_events = 0
    order_activity = 0

    if UserEvent:
        product_views = UserEvent.objects.filter(event_type="VIEW").count()

        cart_activity = UserEvent.objects.filter(
            event_type__in=[
                "ADD_CART",
                "ADD_TO_CART",
                "CART_ADD",
                "REMOVE_CART",
                "REMOVE_FROM_CART",
                "CART_REMOVE",
            ]
        ).count()

        wishlist_activity_events = UserEvent.objects.filter(
            event_type__in=[
                "WISHLIST",
                "ADD_WISHLIST",
                "REMOVE_WISHLIST",
            ]
        ).count()

        order_activity = UserEvent.objects.filter(event_type="ORDER").count()

    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    inactive_products = Product.objects.filter(is_active=False).count()
    out_of_stock_products = Product.objects.filter(stock=0).count()
    low_stock_products = Product.objects.filter(stock__gt=0, stock__lte=5).count()
    discounted_products = Product.objects.filter(discount_price__isnull=False).count()

    total_wishlist_items = Wishlist.objects.count()

    stock_value = (
        Product.objects
        .annotate(item_value=F("effective_price") * F("stock"))
        .aggregate(total=Sum("item_value"))
    )["total"] if False else None

    # Because effective_price is a Python property, Django cannot aggregate it directly.
    stock_value = Decimal("0.00")
    for product in Product.objects.all():
        stock_value += product.effective_price * product.stock

    most_wishlisted_products = (
        Product.objects
        .annotate(wishlist_count=Count("wishlisted_by"))
        .order_by("-wishlist_count")[:5]
    )

    best_rated_products = (
        Product.objects
        .annotate(avg_rating=Avg("reviews__rating"), review_total=Count("reviews"))
        .filter(review_total__gt=0)
        .order_by("-avg_rating")[:5]
    )

    category_analysis = (
        Category.objects
        .annotate(product_count=Count("products"))
        .order_by("-product_count")[:6]
    )

    brand_analysis = (
        Brand.objects
        .annotate(product_count=Count("products"))
        .order_by("-product_count")[:6]
    )

    best_selling_products = get_best_selling_products(OrderItem, UserEvent)
    revenue_chart = get_revenue_chart(Order)

    high_risk = medium_risk = low_risk = 0

    if ChurnScore:
        high_risk = ChurnScore.objects.filter(risk_level="high").count()
        medium_risk = ChurnScore.objects.filter(risk_level="medium").count()
        low_risk = ChurnScore.objects.filter(risk_level="low").count()

    context = {
        "total_sales": total_sales,
        "total_orders": total_orders,
        "total_customers": total_customers,
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "out_of_stock_products": out_of_stock_products,
        "low_stock_products": low_stock_products,
        "discounted_products": discounted_products,
        "total_wishlist_items": total_wishlist_items,
        "product_views": product_views,
        "cart_activity": cart_activity,
        "wishlist_activity_events": wishlist_activity_events,
        "order_activity": order_activity,
        "stock_value": stock_value,
        "most_wishlisted_products": most_wishlisted_products,
        "best_rated_products": best_rated_products,
        "category_analysis": category_analysis,
        "brand_analysis": brand_analysis,
        "best_selling_products": best_selling_products,
        "revenue_chart": revenue_chart,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
    }

    return render(request, "dashboard/analytics.html", context)

@staff_member_required
def admin_profile(request):
    return render(request, "dashboard/admin_profile.html")