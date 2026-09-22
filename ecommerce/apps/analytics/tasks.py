from celery import shared_task

from apps.orders.models import Order
from apps.analytics.services import RevenueService
from apps.loyalty.services import LoyaltyService


@shared_task
def paid_order_created(order_id):
    order = Order.objects.get(id=order_id)
    RevenueService.add_paid_order(order)
    LoyaltyService.award_purchase_points(order)
    LoyaltyService.award_first_purchase_bonus(
        user=order.user,
        order=order,
    )
    print(
        f"Revenue and Loyalty updated for paid Order #{order.id}"
    )

@shared_task
def paid_order_cancelled(order_id):
    order = Order.objects.get(id=order_id)
    RevenueService.remove_paid_order(order)
    print(f"Revenue removed for Order #{order.id}")


@shared_task
def order_refunded(order_id):
    order = Order.objects.get(id=order_id)
    RevenueService.refund_order(order)
    print(f"Revenue refunded for Order #{order.id}")