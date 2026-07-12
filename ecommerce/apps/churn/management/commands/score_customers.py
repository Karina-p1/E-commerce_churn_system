from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.churn.models import ChurnScore
from apps.churn.features import extract_features
from apps.churn.predictor import predict_churn

User = get_user_model()


class Command(BaseCommand):
    help = 'Score all customers for churn risk using their UserEvent data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Print the full computed feature breakdown for each customer'
        )

    def handle(self, *args, **kwargs):
        debug = kwargs.get('debug', False)

        users = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        self.stdout.write(f'Scoring {users.count()} customers...\n')
        high = low = errors = 0

        for user in users:
            try:
                features = extract_features(user)
                result   = predict_churn(features)

                # NOTE: was previously update_or_create(customer=user, ...),
                # which overwrote the customer's one existing row every run
                # and silently discarded all history. Using create() instead
                # keeps a full timeline of scores per customer, which the
                # dashboard's "latest per customer" query already assumed
                # existed, and which the new score-history chart depends on.
                ChurnScore.objects.create(
                    customer=user,
                    score=result['score'],
                    risk_level=result['risk_level'],
                )

                if result['risk_level'] == 'high':
                    high += 1
                else:
                    low += 1

                self.stdout.write(
                    f"  {user.username:<20} "
                    f"{result['risk_level']:<8} "
                    f"score={result['score']}"
                )

                if debug:
                    self.stdout.write("    Raw inputs:")
                    for k, v in features.items():
                        self.stdout.write(f"      {k}: {v}")
                    self.stdout.write("    Computed feature row (model input order):")
                    for k, v in result['debug'].items():
                        self.stdout.write(f"      {k}: {v}")
                    self.stdout.write("")

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"  ERROR for {user.username}: {e}")
                )

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done! High:{high}  Low:{low}  Errors:{errors}'
        ))