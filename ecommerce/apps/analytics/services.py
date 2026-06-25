from collections import defaultdict

from cloudinary.utils import cloudinary_url

from apps.activity.models import UserEvent


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
