import logging

from django import forms
from django.core.mail import send_mail
from django.utils import timezone

from server.models import FeedbackSubmission


logger = logging.getLogger(__name__)


class ContactForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=30, required=False)
    category = forms.ChoiceField(
        choices=FeedbackSubmission.Category.choices,
        initial=FeedbackSubmission.Category.QUESTION,
        required=True,
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        max_length=5000,
        required=True,
    )
    # Honeypot: humans never see/fill this; bots fill all fields.
    website = forms.CharField(required=False)


def send_feedback_email(submission, settings_row):
    """Send a plain-text email notification for a FeedbackSubmission.

    Best-effort: stamps email_delivered_at on success, appends to
    delivery_notes on failure. Never raises.
    """
    to_list = [
        addr.strip()
        for addr in (settings_row.feedback_email_to or '').split(',')
        if addr.strip()
    ]
    from_addr = settings_row.feedback_email_from.strip()
    if not to_list or not from_addr:
        return

    category_label = submission.get_category_display()
    name = f'{submission.first_name} {submission.last_name}'.strip()
    subject = f'[Product Registry] [{category_label}]'
    if name:
        subject = f'{subject} {name}'

    body = (
        f'New {category_label.lower()} from the Product Registry contact form.\n\n'
        f'Name:     {name or "(not provided)"}\n'
        f'Email:    {submission.email}\n'
        f'Phone:    {submission.phone or "(not provided)"}\n'
        f'Category: {category_label}\n'
        f'Received: {submission.created_at:%Y-%m-%d %H:%M:%S %Z}\n\n'
        f'Message:\n'
        f'{submission.message}\n\n'
        f'---\n'
        f'Review in admin: submission #{submission.pk}\n'
    )

    try:
        send_mail(subject, body, from_addr, to_list, fail_silently=False)
    except Exception as exc:
        logger.warning('Feedback email delivery failed for submission %s: %s',
                       submission.pk, exc)
        _append_note(submission, f'email failed: {exc}')
        return

    submission.email_delivered_at = timezone.now()
    submission.save(update_fields=['email_delivered_at'])


def _append_note(submission, text):
    prefix = '\n' if submission.delivery_notes else ''
    submission.delivery_notes = f'{submission.delivery_notes}{prefix}{text}'
    submission.save(update_fields=['delivery_notes'])
