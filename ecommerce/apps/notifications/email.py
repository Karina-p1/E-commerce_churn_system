from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_bulk_html_email(subject, template_name, context, recipients):
    """
    Renders an HTML email template, derives a plain-text fallback from it
    automatically, and sends ONE email BCC'd to every eligible recipient
    (so no customer ever sees another customer's address).

    Recipients are filtered to those who:
      - have a real email address, AND
      - have email_notifications_enabled=True (defaults to True if the
        field doesn't exist yet on an unmigrated User model, so this is
        safe to deploy before/after the accounts migration).

    Sent synchronously. Fine for a small user base; move to a Celery task
    if the recipient list grows large enough that SMTP time becomes
    noticeable on the admin's save request.
    """
    recipient_emails = [
        u.email for u in recipients
        if u.email and getattr(u, 'email_notifications_enabled', True)
    ]

    if not recipient_emails:
        return

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@example.com'

    html_body = render_to_string(template_name, context)
    text_body = strip_tags(html_body)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[from_email],       # nominal "to" — actual recipients are BCC'd
        bcc=recipient_emails,
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)