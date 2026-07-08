from time import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Sum, Avg
from .models import  RevenueSnapshot
from apps.products.models import Product, Category, Brand, Wishlist
from django.apps import apps
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Avg, F
from django.db.models.functions import TruncDate

def analytics_finance(request):

    summary = RevenueSnapshot.objects.aggregate(
        total_revenue=Sum("total_revenue"),
        total_orders=Sum("total_orders"),
        average_order_value=Avg("average_order_value"),
    )

    return render(
        request,
        "analytics/finance.html",
        {
            "summary": summary
        }
    )

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
def analytics_dashboard(request):
    User = get_user_model()

    Order = get_model_or_none("orders", "Order")
    OrderItem = get_model_or_none("orders", "OrderItem")
    UserEvent = get_model_or_none("activity", "UserEvent")

    ChurnScore = (
        get_model_or_none("churn", "ChurnScore")
        or get_model_or_none("churn", "ChurnPrediction")
        or get_model_or_none("churn", "Prediction")
    )

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

    context = {
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
    }

    return render(request, "analytics/dashboard.html", context)

