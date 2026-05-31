from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.churn.models import ChurnScore
from apps.churn.features import extract_features
from apps.churn.predictor import predict_churn

User = get_user_model()


class Command(BaseCommand):
    help = 'Score all customers for churn risk using their UserEvent data'

    def handle(self, *args, **kwargs):
        users = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        self.stdout.write(f'Scoring {users.count()} customers...\n')
        high = medium = low = errors = 0

        for user in users:
            try:
                features = extract_features(user)
                result   = predict_churn(features)

                ChurnScore.objects.create(
                    customer   = user,
                    score      = result['score'],
                    risk_level = result['risk_level'],
                )

                if result['risk_level'] == 'high':
                    high += 1
                elif result['risk_level'] == 'medium':
                    medium += 1
                else:
                    low += 1

                self.stdout.write(
                    f"  {user.username:<20} "
                    f"{result['risk_level']:<8} "
                    f"score={result['score']}"
                )

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"  ERROR for {user.username}: {e}")
                )

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done! High:{high}  Medium:{medium}  Low:{low}  Errors:{errors}'
        ))