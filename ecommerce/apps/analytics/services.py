from collections import defaultdict
from decimal import Decimal

from cloudinary.utils import cloudinary_url
from django.db import transaction
from apps.activity.models import UserEvent
from django.db.models import F, Avg, Sum
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

        today = timezone.localdate()

        with transaction.atomic():

            # -------------------------------
            # Lifetime Revenue Summary
            # -------------------------------

            summary = RevenueService.get_summary()

            RevenueSummary.objects.filter(pk=summary.pk).update(
                total_revenue=F("total_revenue") + order.total_price,
                total_orders=F("total_orders") + 1,
                esewa_revenue=(
                    F("esewa_revenue") + order.total_price
                    if order.payment_method == "ESEWA"
                    else F("esewa_revenue")
                ),
                cod_revenue=(
                    F("cod_revenue") + order.total_price
                    if order.payment_method == "COD"
                    else F("cod_revenue")
                ),
            )

            summary.refresh_from_db()

            summary.average_order_value = (
                summary.total_revenue /
                summary.total_orders
            )

            summary.save(update_fields=["average_order_value"])

            print("✅ RevenueSummary Updated")
            print(f"Revenue : {summary.total_revenue}")
            print(f"Orders  : {summary.total_orders}")

            # -------------------------------
            # Daily Revenue Snapshot
            # -------------------------------

            snapshot, created = RevenueSnapshot.objects.get_or_create(
                date=today,
                defaults={
                    "total_revenue": Decimal("0.00"),
                    "total_orders": 0,
                    "average_order_value": Decimal("0.00"),
                    "esewa_revenue": Decimal("0.00"),
                    "cod_revenue": Decimal("0.00"),
                }
            )

            RevenueSnapshot.objects.filter(pk=snapshot.pk).update(
                total_revenue=F("total_revenue") + order.total_price,
                total_orders=F("total_orders") + 1,
                esewa_revenue=(
                    F("esewa_revenue") + order.total_price
                    if order.payment_method == "ESEWA"
                    else F("esewa_revenue")
                ),
                cod_revenue=(
                    F("cod_revenue") + order.total_price
                    if order.payment_method == "COD"
                    else F("cod_revenue")
                ),
            )

            snapshot.refresh_from_db()

            snapshot.average_order_value = (
                snapshot.total_revenue /
                snapshot.total_orders
            )

            snapshot.save(update_fields=["average_order_value"])

            if created:
                print(f"📅 Created snapshot for {today}")
            else:
                print(f"📅 Updated snapshot for {today}")

            print(f"Today's Revenue : {snapshot.total_revenue}")
            print(f"Today's Orders  : {snapshot.total_orders}")
    
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