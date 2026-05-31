from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity.models import UserEvent
from apps.orders.models import Cart


class Command(BaseCommand):
    help = 'Track abandoned carts older than 24 hours.'

    def handle(self, *args, **kwargs):
        cutoff_time = timezone.now() - timedelta(hours=24)

        carts = Cart.objects.filter(
            items__isnull=False,
            updated_at__lte=cutoff_time
        ).distinct()

        created_count = 0

        for cart in carts:
            already_marked = UserEvent.objects.filter(
                user=cart.user,
                event_type='CART_ABANDONED',
                created_at__gte=cart.updated_at
            ).exists()

            if already_marked:
                continue

            UserEvent.objects.create(
                user=cart.user,
                event_type='CART_ABANDONED'
            )

            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Cart abandonment tracking complete. Created {created_count} CART_ABANDONED events.'
            )
        )