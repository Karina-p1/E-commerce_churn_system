from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

from .models import Complaint
from apps.notifications.models import Notification

_previous_status = {}


@receiver(pre_save, sender=Complaint)
def store_previous_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Complaint.objects.get(pk=instance.pk)
            _previous_status[instance.pk] = old.status
        except Complaint.DoesNotExist:
            pass


@receiver(post_save, sender=Complaint)
def complaint_updated(sender, instance, created, **kwargs):

    if created:
        return

    previous_status = _previous_status.pop(instance.pk, None)

    if previous_status == "RESOLVED":
        return

    if instance.status != "RESOLVED":
        return

    Notification.objects.create(
        recipient=instance.user,
        notif_type="GENERAL",
        title="Complaint Resolved",
        message=f"Your complaint '{instance.subject}' has been resolved."
    )

    html = render_to_string(
        "notifications/emails/complaint_reply.html",
        {
            "user": instance.user,
            "complaint": instance,
        }
    )

    email = EmailMultiAlternatives(
        subject="Complaint Resolved",
        body=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[instance.user.email],
    )

    email.attach_alternative(html, "text/html")
    email.send()