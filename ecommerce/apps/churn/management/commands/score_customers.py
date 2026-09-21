from django.core.management.base import BaseCommand

from apps.churn.services import score_all_customers


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

        # All the actual scoring logic now lives in apps/churn/services.py,
        # shared with the automatic 24-hour Celery task (apps/churn/tasks.py)
        # so manual and automatic runs can never drift apart.
        score_all_customers(debug=debug, log=self.stdout.write)