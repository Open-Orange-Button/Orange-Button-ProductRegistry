# Contact Us form — design

**Status:** Draft
**Date:** 2026-04-20
**Author:** Roman Chikalenko (with Claude)
**Requested by:** Jan Rippingale

## Problem

The OB Product Registry has no way for visitors to reach out — no contact link, no feedback channel, no bug-report path. Jan wants a prominent way for every page visitor to ask questions, report bugs, or send suggestions. Submissions need to reach the team via email and land in GoHighLevel (GHL) as contact records. Site is fully public, unauthenticated, and server-side rendered (Django + Bootstrap 5).

## Goals

- A visible "Contact Us" entry point on every page of the registry.
- A form that collects first name, last name, email (required), phone, category, and a free-text message.
- Every submission is durably stored in our DB so nothing is ever lost.
- Submissions fan out to optional destinations (email, Workato webhook) without code changes when destinations are added or removed.
- Basic spam protection that costs users nothing.
- Non-engineers can change destinations via Django admin.

## Non-goals

- No user accounts, no auth on the form itself.
- No file/screenshot attachments (v1).
- No direct GHL REST integration — GHL fan-out is handled by Workato on the recipe side.
- No CAPTCHA at launch (add only if honeypot proves insufficient).
- No admin dashboard for submissions beyond stock Django admin list/filter/search.
- No rich-text editor in the message field — plain textarea.

## User experience

### Entry point (every page)

A solid accent-colored button labeled **Contact Us** lives in the top navbar, aligned to the right so it stands out without crowding existing nav items. Uses Bootstrap's `btn btn-warning` (orange, matches the Orange Button brand) with a small icon (`bi-envelope` or `bi-chat-dots`).

Implementation: single edit in `server/templates/server/base.html` inside the existing `<nav>` — the button links to `{% url 'product:contact' %}`. No per-page template changes needed.

### Form page (`/product/contact/`)

Single-column form, centered, max-width ~640px. Bootstrap form styling. Fields in order:

| Field | Type | Required | Notes |
|---|---|---|---|
| First name | text | no | max 100 chars |
| Last name | text | no | max 100 chars |
| Email | email | **yes** | Django `EmailField` validation |
| Phone | tel | no | max 30 chars, no format enforcement |
| Category | select | yes | defaults to "General question" |
| Message | textarea | yes | 6 rows, max 5000 chars |
| `website` (honeypot) | text | no | hidden via CSS, off-screen |

Category options:
- `question` — Question *(default)*
- `bug` — Bug report
- `suggestion` — Suggestion
- `other` — Other

Submit button: "Send message", primary style.

Above the form: short heading "Get in touch" and one sentence ("Have a question, bug report, or suggestion? Fill out the form and we'll get back to you.").

### Confirmation page (`/product/contact/thank-you/`)

Follows the Post-Redirect-Get pattern: POST → save → redirect (HTTP 302) → GET. Thank-you page shows a Bootstrap success alert:

> **Thanks, we got your message.**
> We'll reply to the email address you provided. In the meantime, feel free to keep browsing the product registry.
> [Back to products]

Refreshing this page does not resubmit the form.

### Validation errors

On validation failure, re-render the form with Bootstrap `is-invalid` classes on offending fields and Django's field errors displayed inline. All user-entered values are preserved in the re-rendered form; the honeypot field is never echoed back.

## Data model

Two new models in `server/models.py`.

### `FeedbackSubmission`

Canonical record of every successful submission. Written first, before any external call.

```python
class FeedbackSubmission(models.Model):
    class Category(models.TextChoices):
        QUESTION = 'question', 'Question'
        BUG = 'bug', 'Bug report'
        SUGGESTION = 'suggestion', 'Suggestion'
        OTHER = 'other', 'Other'

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.QUESTION)
    message = models.TextField(max_length=5000)

    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    email_delivered_at = models.DateTimeField(null=True, blank=True)
    webhook_delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True)  # failure reasons appended here

    class Meta:
        ordering = ['-created_at']
```

Why `email_delivered_at` / `webhook_delivered_at`: lets Jan see in admin which submissions made it to email/Workato and which didn't, without having to dig through logs.

### `SiteSettings` (singleton)

Editable in Django admin. Singleton enforced by pinning `pk=1`.

```python
class SiteSettings(models.Model):
    feedback_email_to = models.CharField(
        max_length=500, blank=True,
        help_text='Comma-separated recipient email addresses. Blank = do not send email.'
    )
    feedback_email_from = models.EmailField(
        blank=True,
        help_text='From address. Must be verified in AWS SES.'
    )
    workato_webhook_url = models.URLField(
        max_length=500, blank=True,
        help_text='Workato recipe webhook URL. Blank = do not post to Workato.'
    )
    rate_limit_per_hour = models.PositiveIntegerField(
        default=3,
        help_text='Max submissions per IP per hour. 0 = disabled.'
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # prevent deletion

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    class Meta:
        verbose_name = verbose_name_plural = 'Site settings'
```

Cached in-process per request using `functools.lru_cache` keyed on pk, invalidated on model save via a `post_save` signal. (Trivial — avoids a DB round-trip on every submission.)

## Submission flow

1. `POST /product/contact/`
2. View instantiates the Django `Form`; runs validation.
3. **Honeypot check:** if `website` field is non-empty, log `bot_detected`, render the thank-you page anyway (silent drop — don't signal detection to bots).
4. **Rate-limit check:** count `FeedbackSubmission` rows from `source_ip` in the last hour. If `>= rate_limit_per_hour` (and that setting is non-zero), render the form with a generic error ("Too many submissions — please try again later.").
5. **Save** `FeedbackSubmission` row. This is the durable record.
6. **Send email** (best-effort) if `feedback_email_to` is set:
   - Subject: `[Product Registry] [{category_label}] {first_name} {last_name}`.trim()
   - Body: plain-text fields + link back to the admin detail page for the submission.
   - On success, stamp `email_delivered_at`.
   - On failure, append reason to `delivery_notes`, log at WARNING, continue.
7. **POST to Workato** (best-effort) if `workato_webhook_url` is set:
   - JSON payload (schema below).
   - 5-second connect + 10-second read timeout.
   - On success (2xx), stamp `webhook_delivered_at`.
   - On failure, append reason to `delivery_notes`, log at WARNING, continue.
8. Redirect to `/product/contact/thank-you/`.

Failures in steps 6–7 never surface to the user. The DB row is the source of truth; Jan can replay from admin if needed.

### Workato payload

```json
{
  "submitted_at": "2026-04-20T14:22:07Z",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "phone": "+1 555 123 4567",
  "category": "bug",
  "category_label": "Bug report",
  "message": "...",
  "source": "product-registry",
  "submission_id": 1234
}
```

Workato recipe is responsible for mapping these into GHL contact fields, applying tags, and routing by category. Our side doesn't know or care.

## URL routes

Added to `server/urls.py`:

```python
path('contact/', views.contact, name='contact'),
path('contact/thank-you/', views.contact_thank_you, name='contact-thank-you'),
```

## Views

Two function views in `server/views.py`:

- `contact(request)` — GET renders form; POST validates, runs checks, saves, fires destinations, redirects.
- `contact_thank_you(request)` — renders the thank-you template.

Destination fan-out is split into small helpers (`_send_feedback_email`, `_post_to_workato`) that each catch their own exceptions so one failure can't take down the other.

## Templates

New templates under `server/templates/server/`:

- `contact.html` — extends `base.html`, renders form.
- `contact_thank_you.html` — extends `base.html`, renders success alert.

`base.html` gets one new block inside `<nav>` for the "Contact Us" button.

## Admin registration

`server/admin.py`:

- `FeedbackSubmission`
  - `list_display`: created_at, category, email, first_name, last_name, email_delivered_at, webhook_delivered_at
  - `list_filter`: category, created_at, delivery flags
  - `search_fields`: email, first_name, last_name, message
  - `readonly_fields`: everything (submissions are immutable once received)
  - Optional "Resend" admin action (v2, out of scope for v1).
- `SiteSettings`
  - Custom admin that hides the "Add" and "Delete" buttons (singleton).

## Spam protection

Layered, minimal-friction:

1. **Honeypot field** (`website`) — hidden via `style="position:absolute;left:-9999px"` plus `tabindex="-1"` and `autocomplete="off"`. Bots fill it; humans can't see it. Non-empty submissions are silently dropped.
2. **Per-IP rate limit** — 3 submissions/hour by default, configurable in `SiteSettings`. Implemented via a simple `FeedbackSubmission.objects.filter(source_ip=..., created_at__gte=...).count()` check. No external dependencies.
3. **Email field validation** — Django's `EmailField` rejects malformed addresses.
4. **Max message length** — 5000 chars prevents absurdly large payloads.

No CAPTCHA at launch. If spam slips through, add hCaptcha as a second phase.

## Email delivery

Uses Django's `send_mail` with the default email backend. In production, Django's `EMAIL_BACKEND` should be set to `django_ses.SESBackend` (or Django's native `django.core.mail.backends.smtp.EmailBackend` pointed at SES SMTP) — configured via env vars in `settings.py`. Credentials handled by the ECS task role (IAM), not by storing keys.

The `feedback_email_from` address must be verified in SES before the first email succeeds.

## Configuration

All operator-tunable values live in `SiteSettings` (DB, admin-editable). No secrets in env vars, no AWS Secrets Manager.

| Setting | Default | Effect if blank / zero |
|---|---|---|
| `feedback_email_to` | blank | No email sent |
| `feedback_email_from` | blank | No email sent (required if `feedback_email_to` set) |
| `workato_webhook_url` | blank | No Workato POST |
| `rate_limit_per_hour` | 3 | 0 disables rate limiting |

If both email fields and the Workato URL are blank, submissions still save to the DB. Jan can review them manually at `/admin/`.

## Operational concerns

### Superuser for admin access

Django admin requires a superuser. Create one locally for dev and once in production:

```bash
# Local
uv run python manage.py createsuperuser

# Production — via ECS exec or bastion
aws ecs execute-command --cluster ... --task ... --container ... \
    --interactive --command "python manage.py createsuperuser"
```

### Data reload pipeline

`load_local_db_to_remote_db.sql` currently copies local SQLite → prod RDS. Two new tables must be excluded from that script so production config and submissions survive data reloads:

- `server_sitesettings` — prod-only config
- `server_feedbacksubmission` — prod-only submissions

Update the SQL script at the same time the models land.

### Migrations

Two new migrations (one per model) generated via `makemigrations`. Applied automatically on container start by `start.sh` — no manual step.

### Logging

`contact` view logs structured messages at:

- INFO: successful submission (id, category, masked email)
- WARNING: destination delivery failures (which destination, reason)
- INFO: honeypot trip (source_ip, user_agent)
- INFO: rate-limit trip (source_ip)

## Security considerations

- **Form is unauthenticated and public** — intentional; matches Jan's ask.
- **CSRF** — Django's built-in CSRF protection on by default; form uses `{% csrf_token %}`.
- **PII in DB** — submissions contain names, emails, phones. No additional encryption at rest beyond RDS's KMS-backed storage. Acceptable given the site's public/low-sensitivity nature.
- **Workato URL is a secret by obscurity** — anyone with the URL can POST to it. Stored in DB (RDS is in a private VPC), visible only to Django superusers. Accept the tradeoff; Workato-side IP allowlist on BB's NAT egress is a P2 hardening step if needed.
- **Rate limit is per-IP** — imperfect (shared NATs, VPNs) but acceptable for this scale; coupled with honeypot, covers the common case.
- **No sensitive data in logs** — emails masked (`j***@example.com`), no message body in logs.

## Rollout

v1 is a single deployment:

1. Merge branch, Docker image built, pushed to ECR.
2. ECS service update pulls new image.
3. `start.sh` runs `migrate` — creates the two new tables.
4. Roman (or ops) logs into admin once, fills `SiteSettings` (email to/from + optional Workato URL).
5. Feature is live.

No feature flag — the button appearing on every page is the signal to users that the feature shipped.

## Open questions

None blocking. Picked up if they come up later:

- Do we want a `FeedbackSubmission` export-to-CSV admin action for periodic archival?
- Does Jan want a weekly digest email summarizing new submissions?
- Should we retain submissions forever, or prune after N months?

## Out of scope for v1

- Attachments (screenshots, files)
- Multi-language support
- CAPTCHA / external anti-abuse services
- Direct GHL REST integration (Workato handles it)
- Submission replay from admin UI
- Real-time Slack notifications
- CSV export of submissions
