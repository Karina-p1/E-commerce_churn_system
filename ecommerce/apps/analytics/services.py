from collections import defaultdict
from decimal import Decimal

from cloudinary.utils import cloudinary_url

from apps.activity.models import UserEvent
from django.db.models import Avg, Sum
from django.utils import timezone

from apps.orders.models import Order
from .models import RevenueSnapshot, RevenueSummary

def get_top_products(limit=5):
    events = UserEvent.objects.filter(product__isnull=False)

    product_scores = defaultdict(lambda: {
        "product_id": None,
        "product_name": "",
        "product_image": "",
        "product_category": "",
        "views": 0,
        "wishlist": 0,
        "orders": 0,
        "score": 0,
    })

    for e in events.values(
        "product__id",
        "product__name",
        "product__image",
        "product__slug",
        "product__category__name",
        "event_type",
    ):
        pid = e["product__id"]

        product_scores[pid]["product_id"] = pid
        product_scores[pid]["product_name"] = e["product__name"]
        product_scores[pid]["product_slug"] = e["product__slug"]
        product_scores[pid]["product_category"] = e["product__category__name"]

        # Build a real URL from the raw Cloudinary value
        img = e["product__image"]
        if img:
            product_scores[pid]["product_image"] = cloudinary_url(str(img))[0]
        else:
            product_scores[pid]["product_image"] = ""

        if e["event_type"] == "VIEW":
            product_scores[pid]["views"] += 1
        elif e["event_type"] == "WISHLIST":
            product_scores[pid]["wishlist"] += 1
        elif e["event_type"] == "ORDER":
            product_scores[pid]["orders"] += 1

    for p in product_scores.values():
        p["score"] = (
            p["views"] * 1
            + p["wishlist"] * 2
            + p["orders"] * 5
        )

    return sorted(
        product_scores.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:limit]


class RevenueService:

    @staticmethod
    def get_summary():
        summary, created = RevenueSummary.objects.get_or_create(pk=1)
        return summary
    
    @staticmethod
    def add_paid_order(order):

        summary = RevenueService.get_summary()

        summary.total_revenue += order.total_price
        summary.total_orders += 1

        if summary.total_orders > 0:
            summary.average_order_value = (
                summary.total_revenue /
                summary.total_orders
            )

        if order.payment_method == "ESEWA":
            summary.esewa_revenue += order.total_price

        elif order.payment_method == "COD":
            summary.cod_revenue += order.total_price

        summary.save()
    
    @staticmethod
    def remove_paid_order(order):

        summary = RevenueService.get_summary()

        summary.total_revenue -= order.total_price
        summary.total_orders -= 1

        if summary.total_orders > 0:
            summary.average_order_value = (
                summary.total_revenue /
                summary.total_orders
            )
        else:
            summary.average_order_value = Decimal("0.00")

        if order.payment_method == "ESEWA":
            summary.esewa_revenue -= order.total_price

        elif order.payment_method == "COD":
            summary.cod_revenue -= order.total_price

        summary.save()
    @staticmethod
    def refund_order(order):

        summary = RevenueService.get_summary()

        summary.total_revenue -= order.total_price

        if order.payment_method == "ESEWA":
            summary.esewa_revenue -= order.total_price

        elif order.payment_method == "COD":
            summary.cod_revenue -= order.total_price

        if summary.total_orders > 0:
            summary.average_order_value = (
                summary.total_revenue /
                summary.total_orders
            )

        summary.save()
            
    def calculate(self):

        today = timezone.localdate()

        paid_orders = Order.objects.filter(
            payment_status="PAID"
        )

        total_orders = paid_orders.count()

        total_revenue = (
            paid_orders.aggregate(
                total=Sum("total_price")
            )["total"] or 0
        )

        average_order = (
            paid_orders.aggregate(
                avg=Avg("total_price")
            )["avg"] or 0
        )

        esewa = (
            paid_orders.filter(
                payment_method="ESEWA"
            ).aggregate(
                total=Sum("total_price")
            )["total"] or 0
        )

        cod = (
            paid_orders.filter(
                payment_method="COD"
            ).aggregate(
                total=Sum("total_price")
            )["total"] or 0
        )

        RevenueSnapshot.objects.update_or_create(

            date=today,

            defaults={
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "average_order_value": average_order,
                "esewa_revenue": esewa,
                "cod_revenue": cod,
            }
        )

        print("Revenue Analytics Updated")