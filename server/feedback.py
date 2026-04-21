from django import forms

from server.models import FeedbackSubmission


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
