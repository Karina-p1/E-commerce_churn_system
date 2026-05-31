import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.churn.models import UserFeatureSnapshot


class Command(BaseCommand):
    help = 'Export churn feature snapshots to a CSV dataset.'

    def handle(self, *args, **kwargs):
        dataset_dir = os.path.join(settings.BASE_DIR, 'datasets')
        os.makedirs(dataset_dir, exist_ok=True)

        file_path = os.path.join(dataset_dir, 'churn_dataset.csv')

        snapshots = UserFeatureSnapshot.objects.all().select_related('user')

        if not snapshots.exists():
            self.stdout.write(
                self.style.WARNING(
                    'No feature snapshots found. Run: python manage.py build_features'
                )
            )
            return

        with open(file_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)

            writer.writerow([
                'user_id',
                'total_logins',
                'total_product_views',
                'total_product_clicks',
                'total_cart_adds',
                'total_cart_removes',
                'cart_abandonment_count',
                'total_wishlist_adds',
                'total_wishlist_removes',
                'total_orders',
                'checkout_abandonment_count',
                'order_cancel_count',
                'payment_failed_count',
                'total_spent',
                'average_order_value',
                'review_count',
                'average_rating',
                'days_since_last_login',
                'days_since_last_activity',
                'days_since_last_order',
                'click_to_view_rate',
                'cart_to_view_rate',
                'order_to_cart_rate',
                'wishlist_remove_rate',
                'churn_label',
            ])

            for item in snapshots:
                writer.writerow([
                    item.user.id,
                    item.total_logins,
                    item.total_product_views,
                    item.total_product_clicks,
                    item.total_cart_adds,
                    item.total_cart_removes,
                    item.cart_abandonment_count,
                    item.total_wishlist_adds,
                    item.total_wishlist_removes,
                    item.total_orders,
                    item.checkout_abandonment_count,
                    item.order_cancel_count,
                    item.payment_failed_count,
                    float(item.total_spent),
                    float(item.average_order_value),
                    item.review_count,
                    item.average_rating,
                    item.days_since_last_login,
                    item.days_since_last_activity,
                    item.days_since_last_order,
                    item.click_to_view_rate,
                    item.cart_to_view_rate,
                    item.order_to_cart_rate,
                    item.wishlist_remove_rate,
                    int(item.churn_label),
                ])

        self.stdout.write(
            self.style.SUCCESS(
                f'Churn dataset exported successfully: {file_path}'
            )
        )