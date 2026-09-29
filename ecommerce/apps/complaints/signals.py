import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

from .models import Complaint
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

_previous_status = {}


@receiver(pre_save, sender=Complaint)
def store_previous_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Complaint.objects.get(pk=instance.pk)
            _previous_status[instance.pk] = old.status
        except Complaint.DoesNotExist:
            pass


def _rescore_customer(user):
    """
    Re-score one customer right away after their complaint changed
    status, so the churn dashboard reflects it immediately instead of
    waiting for the next scheduled run. Never raises — a scoring
    problem must not break saving the complaint or notifying the user.
    """
    if user.is_staff or user.is_superuser or not user.is_active:
        return  # the churn run only scores active, non-staff customers

    try:
        # Imported here (not at the top) so the ML model is only
        # loaded when it's actually needed, and to avoid a circular
        # import between the complaints and churn apps.
        from apps.churn.services import score_customer
        score_customer(user)
    except Exception:
        logger.exception(
            "Could not re-score customer %s after a complaint update.",
            user.pk,
        )


@receiver(post_save, sender=Complaint)
def complaint_updated(sender, instance, created, **kwargs):

    if created:
        return

    previous_status = _previous_status.pop(instance.pk, None)

    # Only act on a transition INTO resolved or rejected — skip if
    # it was already in that state (avoids re-sending on every save).
    if previous_status == instance.status:
        return

    # The complaint's status changed, which changes the customer's
    # "open complaint" flag used by the churn model — re-score them now.
    # (Runs for every status change, including a reopen back to PENDING.)
    _rescore_customer(instance.user)

    if instance.status not in ("IN_PROGRESS", "RESOLVED", "REJECTED"):
        return

    if instance.status == "IN_PROGRESS":
        title = "Complaint Being Reviewed"
        notif_message = (
            f"Your complaint '{instance.subject}' is now being reviewed "
            f"by our support team."
        )
    elif instance.status == "RESOLVED":
        title = "Complaint Resolved"
        notif_message = f"Your complaint '{instance.subject}' has been resolved."
    else:
        title = "Complaint Rejected"
        notif_message = f"Your complaint '{instance.subject}' has been rejected."
        if instance.admin_reply:
            notif_message += f" Reason: {instance.admin_reply}"

    Notification.objects.create(
        recipient=instance.user,
        notif_type="GENERAL",
        title=title,
        message=notif_message,
    )

    html = render_to_string(
        "notifications/emails/complaint_reply.html",
        {
            "user": instance.user,
            "complaint": instance,
        }
    )

    email = EmailMultiAlternatives(
        subject=title,
        body=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[instance.user.email],
    )

    email.attach_alternative(html, "text/html")
    email.send()