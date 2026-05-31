from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Sum, Avg
from django.utils import timezone

from apps.activity.models import UserEvent
from apps.orders.models import Order
from apps.products.models import Review
from apps.churn.models import UserFeatureSnapshot


User = get_user_model()


def days_since(date_value):
    if not date_value:
        return 999

    return (timezone.now() - date_value).days


def safe_rate(numerator, denominator):
    if denominator == 0:
        return 0

    return round(numerator / denominator, 4)


class Command(BaseCommand):
    help = 'Build ML-ready churn feature snapshots from user activity.'

    def handle(self, *args, **kwargs):
        users = User.objects.all()

        created_count = 0
        updated_count = 0

        for user in users:
            events = UserEvent.objects.filter(user=user)

            total_logins = events.filter(event_type='LOGIN').count()

            total_product_views = events.filter(event_type='VIEW').count()
            total_product_clicks = events.filter(event_type='CLICK').count()

            total_cart_adds = events.filter(event_type='CART').count()
            total_cart_removes = events.filter(event_type='REMOVE_CART').count()
            cart_abandonment_count = events.filter(event_type='CART_ABANDONED').count()

            total_wishlist_adds = events.filter(event_type='WISHLIST').count()
            total_wishlist_removes = events.filter(event_type='REMOVE_WISHLIST').count()

            total_orders = events.filter(event_type='ORDER').count()
            checkout_started_count = events.filter(event_type='CHECKOUT_STARTED').count()
            checkout_abandonment_count = max(checkout_started_count - total_orders, 0)

            order_cancel_count = events.filter(event_type='ORDER_CANCELLED').count()
            payment_failed_count = events.filter(event_type='PAYMENT_FAILED').count()

            last_login = events.filter(
                event_type='LOGIN'
            ).order_by('-created_at').first()

            last_activity = events.order_by('-created_at').first()

            last_order = events.filter(
                event_type='ORDER'
            ).order_by('-created_at').first()

            orders = Order.objects.filter(user=user)

            total_spent = orders.aggregate(
                total=Sum('total_price')
            )['total'] or 0

            average_order_value = orders.aggregate(
                avg=Avg('total_price')
            )['avg'] or 0

            reviews = Review.objects.filter(customer=user)

            review_count = reviews.count()

            average_rating = reviews.aggregate(
                avg=Avg('rating')
            )['avg'] or 0

            days_since_last_login = days_since(
                last_login.created_at if last_login else None
            )

            days_since_last_activity = days_since(
                last_activity.created_at if last_activity else None
            )

            days_since_last_order = days_since(
                last_order.created_at if last_order else None
            )

            click_to_view_rate = safe_rate(
                total_product_clicks,
                total_product_views
            )

            cart_to_view_rate = safe_rate(
                total_cart_adds,
                total_product_views
            )

            order_to_cart_rate = safe_rate(
                total_orders,
                total_cart_adds
            )

            wishlist_remove_rate = safe_rate(
                total_wishlist_removes,
                total_wishlist_adds
            )

            # Basic churn rule for training label:
            # If user has not ordered in more than 30 days, mark as churned.
            churn_label = days_since_last_order > 30

            snapshot, created = UserFeatureSnapshot.objects.update_or_create(
                user=user,
                defaults={
                    'total_logins': total_logins,

                    'total_product_views': total_product_views,
                    'total_product_clicks': total_product_clicks,

                    'total_cart_adds': total_cart_adds,
                    'total_cart_removes': total_cart_removes,
                    'cart_abandonment_count': cart_abandonment_count,

                    'total_wishlist_adds': total_wishlist_adds,
                    'total_wishlist_removes': total_wishlist_removes,

                    'total_orders': total_orders,
                    'checkout_abandonment_count': checkout_abandonment_count,
                    'order_cancel_count': order_cancel_count,
                    'payment_failed_count': payment_failed_count,

                    'total_spent': total_spent,
                    'average_order_value': average_order_value,

                    'review_count': review_count,
                    'average_rating': round(average_rating, 2),

                    'days_since_last_login': days_since_last_login,
                    'days_since_last_activity': days_since_last_activity,
                    'days_since_last_order': days_since_last_order,

                    'click_to_view_rate': click_to_view_rate,
                    'cart_to_view_rate': cart_to_view_rate,
                    'order_to_cart_rate': order_to_cart_rate,
                    'wishlist_remove_rate': wishlist_remove_rate,

                    'churn_label': churn_label,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Feature build complete. Created: {created_count}, Updated: {updated_count}'
            )
        )