import os

import joblib
import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.churn.models import UserFeatureSnapshot, ChurnPrediction


class Command(BaseCommand):
    help = 'Predict churn risk for all users using the trained model.'

    def handle(self, *args, **kwargs):
        model_path = os.path.join(
            settings.BASE_DIR,
            'ml_models',
            'churn_model.pkl'
        )

        if not os.path.exists(model_path):
            self.stdout.write(
                self.style.ERROR(
                    'Model not found. Run: python manage.py train_churn_model'
                )
            )
            return

        model = joblib.load(model_path)

        snapshots = UserFeatureSnapshot.objects.all().select_related('user')

        if not snapshots.exists():
            self.stdout.write(
                self.style.ERROR(
                    'No feature snapshots found. Run: python manage.py build_features'
                )
            )
            return

        created_count = 0

        for item in snapshots:
            row = pd.DataFrame([{
                'total_logins': item.total_logins,
                'total_product_views': item.total_product_views,
                'total_product_clicks': item.total_product_clicks,
                'total_cart_adds': item.total_cart_adds,
                'total_cart_removes': item.total_cart_removes,
                'cart_abandonment_count': item.cart_abandonment_count,
                'total_wishlist_adds': item.total_wishlist_adds,
                'total_wishlist_removes': item.total_wishlist_removes,
                'total_orders': item.total_orders,
                'checkout_abandonment_count': item.checkout_abandonment_count,
                'order_cancel_count': item.order_cancel_count,
                'payment_failed_count': item.payment_failed_count,
                'total_spent': float(item.total_spent),
                'average_order_value': float(item.average_order_value),
                'review_count': item.review_count,
                'average_rating': item.average_rating,
                'days_since_last_login': item.days_since_last_login,
                'days_since_last_activity': item.days_since_last_activity,
                'days_since_last_order': item.days_since_last_order,
                'click_to_view_rate': item.click_to_view_rate,
                'cart_to_view_rate': item.cart_to_view_rate,
                'order_to_cart_rate': item.order_to_cart_rate,
                'wishlist_remove_rate': item.wishlist_remove_rate,
            }])

            probability = model.predict_proba(row)[0][1]
            prediction = probability >= 0.5

            ChurnPrediction.objects.create(
                user=item.user,
                probability=probability,
                prediction=prediction
            )

            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Churn predictions created successfully. Total: {created_count}'
            )
        )