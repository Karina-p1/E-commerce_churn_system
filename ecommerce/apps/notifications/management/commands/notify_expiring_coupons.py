from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.orders.models import Coupon
from apps.notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Notify registered users about active limited-time offers expiring '
        'within the next 3 days. Intended to run daily via cron.'
    )

    def handle(self, *args, **kwargs):
        now = timezone.now()
        soon = now + timezone.timedelta(days=3)

        expiring_coupons = Coupon.objects.filter(
            is_active=True,
            valid_until__isnull=False,
            valid_until__lte=soon,
            valid_until__gte=now,
        )

        if not expiring_coupons.exists():
            self.stdout.write('No coupons expiring soon.')
            return

        recipients = list(
            User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        )
        total_sent = 0

        for coupon in expiring_coupons:
            # Only send the expiry reminder once per coupon, ever — otherwise
            # this would re-notify everyone every day until the coupon expires.
            already_notified = Notification.objects.filter(
                coupon=coupon, notif_type='OFFER_EXPIRING'
            ).exists()

            if already_notified:
                continue

            Notification.objects.bulk_create([
                Notification(
                    recipient=user,
                    notif_type='OFFER_EXPIRING',
                    title='Offer expiring soon!',
                    message=(
                        f"Code {coupon.code} expires "
                        f"{coupon.valid_until:%b %d, %Y} \u2014 use it before it's gone."
                    ),
                    coupon=coupon,
                )
                for user in recipients
            ])
            total_sent += len(recipients)

        self.stdout.write(
            self.style.SUCCESS(f'Sent {total_sent} expiry-reminder notifications.')
        )