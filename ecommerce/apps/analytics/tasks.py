from celery import shared_task

from apps.orders.models import Order
from apps.analytics.services import RevenueService
from apps.loyalty.services import LoyaltyService


@shared_task
def paid_order_created(order_id):
    order = Order.objects.get(id=order_id)

    RevenueService.add_paid_order(order)

    if order.loyalty_points_redeemed > 0:
        LoyaltyService.redeem_points(
            user=order.user,
            points=order.loyalty_points_redeemed,
            description=f"Loyalty points redeemed for Order #{order.id}",
            order=order,
        )

    LoyaltyService.award_purchase_points(order)

    LoyaltyService.award_first_purchase_bonus(
        user=order.user,
        order=order,
    )

    print(f"Revenue & Loyalty updated for paid Order #{order.id}")

@shared_task
def paid_order_cancelled(order_id):
    order = Order.objects.get(id=order_id)
    RevenueService.remove_paid_order(order)
    print(f"Revenue removed for Order #{order.id}")


@shared_task
def order_refunded(order_id):
    order = Order.objects.get(id=order_id)

    RevenueService.refund_order(order)

    LoyaltyService.reverse_order_points(
        order=order,
        description=f"Loyalty points reversed for refunded Order #{order.id}",
    )

    print(
        f"Revenue & Loyalty refunded for Order #{order.id}"
    )