# Contact Us Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a prominent "Contact Us" button on every page of the OB Product Registry that leads to a form collecting name/email/phone/category/message. Submissions are durably saved to the DB and optionally fan out to email + a Workato webhook (both configured via Django admin).

**Architecture:** Two new Django models (`FeedbackSubmission` for submissions, `SiteSettings` singleton for admin-editable destinations), a single form view with honeypot and per-IP rate-limiting, and small delivery helpers that fail independently so one broken destination can't take down another. The canonical record is always the DB row; email + webhook are best-effort.

**Tech Stack:** Python 3.14, Django 6, Bootstrap 5 (templates), SQLite (dev) / MySQL 8.4 on RDS (prod), `django.test.TestCase` for tests, `uv` for dependency management. HTTP calls use `urllib.request` from the stdlib (no new dependency).

**Spec:** `docs/superpowers/specs/2026-04-20-contact-us-form-design.md`

## File structure

| File | Action | Responsibility |
|---|---|---|
| `server/models.py` | modify (append) | `FeedbackSubmission` + `SiteSettings` models |
| `server/migrations/XXXX_*.py` | create (generated) | Django migration for both new models |
| `server/admin.py` | replace content | Register `FeedbackSubmission` + `SiteSettings` with singleton-safe admin |
| `server/feedback.py` | create (new module) | `ContactForm` class + `_send_feedback_email` + `_post_to_workato` helpers (keeps `views.py` focused) |
| `server/views.py` | modify (append) | `contact` + `contact_thank_you` view functions |
| `server/urls.py` | modify | Add 2 new `path(...)` entries |
| `server/templates/server/base.html` | modify | Add "Contact Us" button in navbar |
| `server/templates/server/contact.html` | create | Form page template |
| `server/templates/server/contact_thank_you.html` | create | Thank-you page template |
| `product_registry/settings.py` | modify | Env-driven email backend config |
| `load_local_db_to_remote_db.sql` | modify | Comment noting new tables are prod-only |
| `server/tests.py` | replace content | All Django `TestCase`s for the feature |

**Deviation from spec:** The spec mentions caching `SiteSettings.get()` via `functools.lru_cache` + a `post_save` signal. For v1 this is YAGNI — the query is one indexed row lookup, sub-millisecond. We'll call `SiteSettings.get()` directly each submission. If profiling ever shows it matters, add caching later.

## Test strategy

- Use Django's built-in `django.test.TestCase` (the project already has a stub `server/tests.py`).
- Run all tests: `uv run python manage.py test server`
- Run one test: `uv run python manage.py test server.tests.ContactFormTests.test_get_returns_200`
- Use `django.test.Client` for HTTP-level tests.
- Use `django.core.mail` locmem backend (`override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')`) for email tests; Django's `mail.outbox` lets us assert what was sent.
- For webhook tests, mock `urllib.request.urlopen` with `unittest.mock.patch`.

---

## Task 1: Test scaffold — verify the test runner works

**Files:**
- Modify: `server/tests.py`

- [ ] **Step 1: Replace the stub test file with a placeholder that actually runs**

Replace entire contents of `server/tests.py` with:

```python
from django.test import TestCase


class SmokeTests(TestCase):
    def test_runner_works(self):
        self.assertEqual(1 + 1, 2)
```

- [ ] **Step 2: Run the test to confirm the harness works**

Run: `uv run python manage.py test server.tests.SmokeTests -v 2`
Expected: `Ran 1 test in ... OK`

- [ ] **Step 3: Commit**

```bash
git add server/tests.py
git commit -m "Add test scaffold for Contact Us feature"
```

---

## Task 2: `FeedbackSubmission` model

**Files:**
- Modify: `server/models.py` (append at end)
- Create: `server/migrations/XXXX_feedbacksubmission.py` (generated)
- Modify: `server/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
from server.models import FeedbackSubmission


class FeedbackSubmissionModelTests(TestCase):
    def test_create_with_all_fields(self):
        row = FeedbackSubmission.objects.create(
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            phone='+1-555-0100',
            category=FeedbackSubmission.Category.BUG,
            message='Found a bug.',
            source_ip='203.0.113.7',
            user_agent='Mozilla/5.0',
        )
        self.assertIsNotNone(row.pk)
        self.assertIsNotNone(row.created_at)
        self.assertEqual(row.category, 'bug')
        self.assertIsNone(row.email_delivered_at)
        self.assertIsNone(row.webhook_delivered_at)
        self.assertEqual(row.delivery_notes, '')

    def test_category_defaults_to_question(self):
        row = FeedbackSubmission.objects.create(
            email='x@example.com',
            message='Hi',
        )
        self.assertEqual(row.category, 'question')

    def test_ordering_newest_first(self):
        old = FeedbackSubmission.objects.create(email='a@x.com', message='old')
        new = FeedbackSubmission.objects.create(email='b@x.com', message='new')
        rows = list(FeedbackSubmission.objects.all())
        self.assertEqual(rows[0].pk, new.pk)
        self.assertEqual(rows[1].pk, old.pk)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python manage.py test server.tests.FeedbackSubmissionModelTests -v 2`
Expected: ImportError / AttributeError — `FeedbackSubmission` does not exist.

- [ ] **Step 3: Add the model**

Append to `server/models.py`:

```python
class FeedbackSubmission(models.Model):
    class Category(models.TextChoices):
        QUESTION = 'question', _('Question')
        BUG = 'bug', _('Bug report')
        SUGGESTION = 'suggestion', _('Suggestion')
        OTHER = 'other', _('Other')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.QUESTION
    )
    message = models.TextField(max_length=5000)

    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    email_delivered_at = models.DateTimeField(null=True, blank=True)
    webhook_delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_category_display()} from {self.email} at {self.created_at:%Y-%m-%d %H:%M}'
```

- [ ] **Step 4: Generate the migration**

Run: `uv run python manage.py makemigrations server`
Expected: `Migrations for 'server': server/migrations/XXXX_feedbacksubmission.py - Create model FeedbackSubmission`

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.FeedbackSubmissionModelTests -v 2`
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 6: Commit**

```bash
git add server/models.py server/migrations/ server/tests.py
git commit -m "Add FeedbackSubmission model"
```

---

## Task 3: `SiteSettings` singleton model

**Files:**
- Modify: `server/models.py` (append)
- Create: `server/migrations/XXXX_sitesettings.py` (generated)
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
from server.models import SiteSettings


class SiteSettingsModelTests(TestCase):
    def test_get_creates_singleton_if_missing(self):
        s = SiteSettings.get()
        self.assertEqual(s.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_get_returns_existing(self):
        SiteSettings.objects.create(feedback_email_to='x@y.com')
        s = SiteSettings.get()
        self.assertEqual(s.feedback_email_to, 'x@y.com')
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_save_always_pins_pk_to_1(self):
        s = SiteSettings(pk=42, feedback_email_to='a@b.com')
        s.save()
        self.assertEqual(s.pk, 1)

    def test_delete_is_noop(self):
        s = SiteSettings.get()
        s.delete()
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_defaults(self):
        s = SiteSettings.get()
        self.assertEqual(s.feedback_email_to, '')
        self.assertEqual(s.feedback_email_from, '')
        self.assertEqual(s.workato_webhook_url, '')
        self.assertEqual(s.rate_limit_per_hour, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.SiteSettingsModelTests -v 2`
Expected: ImportError — `SiteSettings` does not exist.

- [ ] **Step 3: Add the model**

Append to `server/models.py`:

```python
class SiteSettings(models.Model):
    feedback_email_to = models.CharField(
        max_length=500,
        blank=True,
        help_text='Comma-separated recipient email addresses. Blank = do not send email.',
    )
    feedback_email_from = models.EmailField(
        blank=True,
        help_text='From address. Must be verified in AWS SES.',
    )
    workato_webhook_url = models.URLField(
        max_length=500,
        blank=True,
        help_text='Workato recipe webhook URL. Blank = do not post to Workato.',
    )
    rate_limit_per_hour = models.PositiveIntegerField(
        default=3,
        help_text='Max submissions per IP per hour. 0 = disabled.',
    )

    class Meta:
        verbose_name = 'Site settings'
        verbose_name_plural = 'Site settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return  # singleton: never deletable

    @classmethod
    def get(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Site settings'
```

- [ ] **Step 4: Generate the migration**

Run: `uv run python manage.py makemigrations server`
Expected: new migration file adding `SiteSettings`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.SiteSettingsModelTests -v 2`
Expected: `Ran 5 tests in ... OK`

- [ ] **Step 6: Commit**

```bash
git add server/models.py server/migrations/ server/tests.py
git commit -m "Add SiteSettings singleton model"
```

---

## Task 4: Admin registration

**Files:**
- Modify: `server/admin.py` (replace contents)
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
from django.contrib.auth import get_user_model


class AdminRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(
            username='admin', password='pw', email='admin@example.com'
        )

    def test_feedbacksubmission_admin_changelist_accessible(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/server/feedbacksubmission/')
        self.assertEqual(resp.status_code, 200)

    def test_sitesettings_admin_redirects_to_singleton(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/server/sitesettings/', follow=True)
        self.assertEqual(resp.status_code, 200)

    def test_sitesettings_change_page_uses_pk_1(self):
        self.client.force_login(self.admin)
        SiteSettings.get()  # ensure row exists
        resp = self.client.get('/admin/server/sitesettings/1/change/')
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.AdminRegistrationTests -v 2`
Expected: 404s — models not registered.

- [ ] **Step 3: Register the models**

Replace entire contents of `server/admin.py` with:

```python
from django.contrib import admin

from server.models import FeedbackSubmission, SiteSettings


@admin.register(FeedbackSubmission)
class FeedbackSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'category',
        'email',
        'first_name',
        'last_name',
        'email_delivered_at',
        'webhook_delivered_at',
    )
    list_filter = ('category', 'created_at', 'email_delivered_at', 'webhook_delivered_at')
    search_fields = ('email', 'first_name', 'last_name', 'message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = (
        'created_at', 'first_name', 'last_name', 'email', 'phone',
        'category', 'message', 'source_ip', 'user_agent',
        'email_delivered_at', 'webhook_delivered_at', 'delivery_notes',
    )

    def has_add_permission(self, request):
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Singleton: hide "Add" if a row already exists
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Auto-redirect the changelist to the single instance's change page
        from django.shortcuts import redirect
        SiteSettings.get()  # ensure pk=1 exists
        return redirect('admin:server_sitesettings_change', object_id=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.AdminRegistrationTests -v 2`
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/admin.py server/tests.py
git commit -m "Register FeedbackSubmission and SiteSettings in admin"
```

---

## Task 5: `ContactForm` class

**Files:**
- Create: `server/feedback.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
from server.feedback import ContactForm


class ContactFormTests(TestCase):
    VALID = {
        'first_name': 'Jane',
        'last_name': 'Doe',
        'email': 'jane@example.com',
        'phone': '+1-555-0100',
        'category': 'question',
        'message': 'Hello there.',
        'website': '',
    }

    def test_valid_form(self):
        form = ContactForm(data=self.VALID)
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_is_required(self):
        data = dict(self.VALID, email='')
        form = ContactForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_message_is_required(self):
        data = dict(self.VALID, message='')
        form = ContactForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_names_and_phone_are_optional(self):
        data = dict(self.VALID, first_name='', last_name='', phone='')
        form = ContactForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_must_be_valid(self):
        data = dict(self.VALID, email='not-an-email')
        form = ContactForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_category_must_be_in_choices(self):
        data = dict(self.VALID, category='bogus')
        form = ContactForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_message_max_length_5000(self):
        data = dict(self.VALID, message='x' * 5001)
        form = ContactForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_honeypot_field_present(self):
        form = ContactForm()
        self.assertIn('website', form.fields)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.ContactFormTests -v 2`
Expected: ImportError — `server.feedback` module does not exist.

- [ ] **Step 3: Create the form module**

Create `server/feedback.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.ContactFormTests -v 2`
Expected: `Ran 8 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/feedback.py server/tests.py
git commit -m "Add ContactForm class"
```

---

## Task 6: Contact URL route + GET view

**Files:**
- Modify: `server/urls.py`
- Modify: `server/views.py` (append)
- Modify: `server/tests.py` (append)

Note: the template doesn't exist yet. The view will fail at render time until Task 7. We split them because the URL + view wiring is one concern and the template is another, and this keeps each task small.

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
from django.urls import reverse


class ContactViewGetTests(TestCase):
    def test_get_reverses_to_url(self):
        self.assertEqual(reverse('product:contact'), '/product/contact/')

    def test_get_returns_200_and_form(self):
        resp = self.client.get('/product/contact/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)
        self.assertContains(resp, 'Get in touch')
        self.assertContains(resp, 'name="email"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python manage.py test server.tests.ContactViewGetTests -v 2`
Expected: `NoReverseMatch` — the URL isn't registered yet.

- [ ] **Step 3: Add the URL route**

Edit `server/urls.py`. After the existing routes in `urlpatterns`, add two entries. The full file should look like:

```python
from django.urls import path

from . import views


app_name = 'product'
urlpatterns = [
    path('', views.product_list, name='list'),
    path('us-domestic-content/', views.product_list_us_domestic, name='list-us-domestic'),
    path('contact/', views.contact, name='contact'),
    path('contact/thank-you/', views.contact_thank_you, name='contact-thank-you'),
    path('<uuid:ProdID_Value>/', views.product_detail_by_ProdID, name='detail-prodid'),
    path('<uuid:ProdID_Value>/json/', views.product_json, name='json'),
    path('<slug:ProdCode_Value>/', views.product_detail_by_ProdCode, name='detail-prodcode'),
]
```

The `contact/` and `contact/thank-you/` routes must come BEFORE the `<slug:ProdCode_Value>` catch-all, otherwise Django matches `contact` as a ProdCode slug.

- [ ] **Step 4: Add the GET view**

Append to `server/views.py`:

```python
from server.feedback import ContactForm


def contact(request):
    form = ContactForm()
    return render(request, 'server/contact.html', context={'form': form})


def contact_thank_you(request):
    return render(request, 'server/contact_thank_you.html')
```

- [ ] **Step 5: Run the test to verify the URL reverse passes**

Run: `uv run python manage.py test server.tests.ContactViewGetTests.test_get_reverses_to_url -v 2`
Expected: PASS.

The other test (`test_get_returns_200_and_form`) will still fail because the template doesn't exist yet. That's fine — we'll fix it in Task 7.

- [ ] **Step 6: Commit**

```bash
git add server/urls.py server/views.py server/tests.py
git commit -m "Wire /product/contact/ URL and GET view"
```

---

## Task 7: Contact form template

**Files:**
- Create: `server/templates/server/contact.html`

- [ ] **Step 1: Create the template**

Create `server/templates/server/contact.html`:

```html
{% extends 'server/base.html' %}

{% block title %}Contact Us - Product Registry{% endblock %}

{% block main %}
<div class='container' style='max-width: 640px;'>
    <div class='row mt-4'>
        <div class='col-12'>
            <h1>Get in touch</h1>
            <p class='text-muted'>
                Have a question, bug report, or suggestion?
                Fill out the form and we'll get back to you.
            </p>

            <form method='POST' action="{% url 'product:contact' %}" novalidate>
                {% csrf_token %}

                <div class='row'>
                    <div class='col-md-6 mb-3'>
                        <label for='id_first_name' class='form-label'>First name</label>
                        <input type='text' name='first_name' id='id_first_name'
                               value='{{ form.first_name.value|default_if_none:"" }}'
                               class='form-control {% if form.first_name.errors %}is-invalid{% endif %}'
                               maxlength='100'>
                        {% for e in form.first_name.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                    </div>
                    <div class='col-md-6 mb-3'>
                        <label for='id_last_name' class='form-label'>Last name</label>
                        <input type='text' name='last_name' id='id_last_name'
                               value='{{ form.last_name.value|default_if_none:"" }}'
                               class='form-control {% if form.last_name.errors %}is-invalid{% endif %}'
                               maxlength='100'>
                        {% for e in form.last_name.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                    </div>
                </div>

                <div class='mb-3'>
                    <label for='id_email' class='form-label'>
                        Email <span class='text-danger'>*</span>
                    </label>
                    <input type='email' name='email' id='id_email' required
                           value='{{ form.email.value|default_if_none:"" }}'
                           class='form-control {% if form.email.errors %}is-invalid{% endif %}'>
                    {% for e in form.email.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                </div>

                <div class='mb-3'>
                    <label for='id_phone' class='form-label'>Phone</label>
                    <input type='tel' name='phone' id='id_phone'
                           value='{{ form.phone.value|default_if_none:"" }}'
                           class='form-control {% if form.phone.errors %}is-invalid{% endif %}'
                           maxlength='30'>
                    {% for e in form.phone.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                </div>

                <div class='mb-3'>
                    <label for='id_category' class='form-label'>
                        Category <span class='text-danger'>*</span>
                    </label>
                    <select name='category' id='id_category' required
                            class='form-select {% if form.category.errors %}is-invalid{% endif %}'>
                        {% for value, label in form.fields.category.choices %}
                        <option value='{{ value }}'
                            {% if form.category.value == value %}selected{% endif %}>
                            {{ label }}
                        </option>
                        {% endfor %}
                    </select>
                    {% for e in form.category.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                </div>

                <div class='mb-3'>
                    <label for='id_message' class='form-label'>
                        Message <span class='text-danger'>*</span>
                    </label>
                    <textarea name='message' id='id_message' rows='6' required maxlength='5000'
                              class='form-control {% if form.message.errors %}is-invalid{% endif %}'>{{ form.message.value|default_if_none:"" }}</textarea>
                    {% for e in form.message.errors %}<div class='invalid-feedback'>{{ e }}</div>{% endfor %}
                </div>

                {# Honeypot: hidden from humans, filled only by bots. #}
                <div style='position:absolute;left:-9999px;top:-9999px;' aria-hidden='true'>
                    <label for='id_website'>Website</label>
                    <input type='text' name='website' id='id_website'
                           tabindex='-1' autocomplete='off'>
                </div>

                {% if form.non_field_errors %}
                <div class='alert alert-danger'>
                    {% for e in form.non_field_errors %}{{ e }}<br>{% endfor %}
                </div>
                {% endif %}

                <button type='submit' class='btn btn-primary'>Send message</button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
```

Note: the honeypot is deliberately NOT echoed back on re-render — we don't output its previous value, because a bot value should not survive a form re-render.

- [ ] **Step 2: Run the test**

Run: `uv run python manage.py test server.tests.ContactViewGetTests -v 2`
Expected: `Ran 2 tests in ... OK`

- [ ] **Step 3: Manually open the page to sanity-check it renders**

Run: `uv run python manage.py runserver`
Visit: `http://127.0.0.1:8000/product/contact/`
Expected: the form renders, no server errors, the honeypot field is not visible.
Stop the server with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add server/templates/server/contact.html
git commit -m "Add contact form template"
```

---

## Task 8: Thank-you page

**Files:**
- Create: `server/templates/server/contact_thank_you.html`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
class ContactThankYouViewTests(TestCase):
    def test_reverses_to_url(self):
        self.assertEqual(reverse('product:contact-thank-you'), '/product/contact/thank-you/')

    def test_returns_200_with_success_message(self):
        resp = self.client.get('/product/contact/thank-you/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Thanks, we got your message')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.ContactThankYouViewTests -v 2`
Expected: the 200 test fails — `TemplateDoesNotExist`.

- [ ] **Step 3: Create the template**

Create `server/templates/server/contact_thank_you.html`:

```html
{% extends 'server/base.html' %}

{% block title %}Message received - Product Registry{% endblock %}

{% block main %}
<div class='container' style='max-width: 640px;'>
    <div class='row mt-4'>
        <div class='col-12'>
            <div class='alert alert-success'>
                <h4 class='alert-heading'>Thanks, we got your message.</h4>
                <p class='mb-2'>
                    We'll reply to the email address you provided. In the meantime,
                    feel free to keep browsing the product registry.
                </p>
                <a href="{% url 'product:list' %}" class='btn btn-primary btn-sm'>Back to products</a>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.ContactThankYouViewTests -v 2`
Expected: `Ran 2 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/templates/server/contact_thank_you.html server/tests.py
git commit -m "Add contact thank-you page"
```

---

## Task 9: "Contact Us" button in the navbar

**Files:**
- Modify: `server/templates/server/base.html`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
class ContactButtonTests(TestCase):
    def test_button_present_on_product_list(self):
        resp = self.client.get('/product/')
        self.assertContains(resp, 'Contact Us')
        self.assertContains(resp, 'href="/product/contact/"')

    def test_button_present_on_us_domestic(self):
        resp = self.client.get('/product/us-domestic-content/')
        self.assertContains(resp, 'Contact Us')

    def test_button_present_on_contact_page_itself(self):
        resp = self.client.get('/product/contact/')
        self.assertContains(resp, 'Contact Us')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.ContactButtonTests -v 2`
Expected: `Contact Us` not found.

- [ ] **Step 3: Edit the navbar**

In `server/templates/server/base.html`, locate the closing `</div>` of `<div class='collapse navbar-collapse' id='navbarSupportedContent'>` (currently around line 35). Replace the whole `<div class='collapse navbar-collapse' ...>` block with:

```html
            <div class='collapse navbar-collapse' id='navbarSupportedContent'>
                <ul class='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li class='nav-item'>
                        <a class='nav-link {% block navbar-product-list-active %}{% endblock %}' aria-current='page' href="{% url 'product:list' %}">Products</a>
                    </li>
                    <li class='nav-item'>
                        <a class='nav-link {% block navbar-product-list-us-domestic-active %}{% endblock %}' aria-current='page' href="{% url 'product:list-us-domestic' %}">US Domestic Content</a>
                    </li>
                </ul>
                <a href="{% url 'product:contact' %}" class='btn btn-warning fw-semibold'>
                    <i class='bi bi-envelope'></i> Contact Us
                </a>
            </div>
```

The only addition is the `<a href=... class='btn btn-warning fw-semibold'>` after the `</ul>`. `me-auto` on the `<ul>` pushes the button to the right.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.ContactButtonTests -v 2`
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 5: Manually verify visual**

Run: `uv run python manage.py runserver`
Visit: `http://127.0.0.1:8000/product/` — orange "Contact Us" button appears top-right of navbar.
Click it — lands on the form page.
Stop server.

- [ ] **Step 6: Commit**

```bash
git add server/templates/server/base.html server/tests.py
git commit -m "Add Contact Us button to navbar on every page"
```

---

## Task 10: POST handler — save submission and redirect

**Files:**
- Modify: `server/views.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
class ContactPostTests(TestCase):
    VALID = {
        'first_name': 'Jane',
        'last_name': 'Doe',
        'email': 'jane@example.com',
        'phone': '+1-555-0100',
        'category': 'question',
        'message': 'Hello there.',
        'website': '',
    }

    def test_valid_post_creates_submission(self):
        resp = self.client.post('/product/contact/', data=self.VALID)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/product/contact/thank-you/')
        self.assertEqual(FeedbackSubmission.objects.count(), 1)
        row = FeedbackSubmission.objects.get()
        self.assertEqual(row.email, 'jane@example.com')
        self.assertEqual(row.category, 'question')
        self.assertEqual(row.message, 'Hello there.')

    def test_valid_post_captures_source_ip_and_user_agent(self):
        self.client.post(
            '/product/contact/',
            data=self.VALID,
            REMOTE_ADDR='198.51.100.42',
            HTTP_USER_AGENT='TestAgent/1.0',
        )
        row = FeedbackSubmission.objects.get()
        self.assertEqual(row.source_ip, '198.51.100.42')
        self.assertEqual(row.user_agent, 'TestAgent/1.0')

    def test_invalid_post_rerenders_form_no_row_saved(self):
        data = dict(self.VALID, email='')
        resp = self.client.post('/product/contact/', data=data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FeedbackSubmission.objects.count(), 0)
        self.assertContains(resp, 'Get in touch')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.ContactPostTests -v 2`
Expected: fail — the view is GET-only right now, so a POST also just renders GET.

- [ ] **Step 3: Update the `contact` view to handle POST**

In `server/views.py`, add a logger near the top of the file (after existing imports):

```python
import logging

logger = logging.getLogger(__name__)
```

Then replace the existing `contact` function with the following. Note that `server.models` is already imported at the top of `views.py` as `import server.models as models`, so we access the new model via `models.FeedbackSubmission`:

```python
def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _mask_email(addr):
    if not addr or '@' not in addr:
        return addr or ''
    local, _, domain = addr.partition('@')
    if not local:
        return addr
    return f'{local[0]}***@{domain}'


def contact(request):
    if request.method == 'POST':
        form = ContactForm(data=request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            submission = models.FeedbackSubmission.objects.create(
                first_name=cd['first_name'],
                last_name=cd['last_name'],
                email=cd['email'],
                phone=cd['phone'],
                category=cd['category'],
                message=cd['message'],
                source_ip=_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
            logger.info(
                'contact submission saved id=%s category=%s email=%s',
                submission.pk, submission.category, _mask_email(submission.email),
            )
            return HttpResponseRedirect(reverse('product:contact-thank-you'))
    else:
        form = ContactForm()
    return render(request, 'server/contact.html', context={'form': form})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.ContactPostTests -v 2`
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/views.py server/tests.py
git commit -m "Save contact form submissions and redirect to thank-you"
```

---

## Task 11: Honeypot check

**Files:**
- Modify: `server/views.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
class HoneypotTests(TestCase):
    VALID_WITH_BOT = {
        'first_name': '',
        'last_name': '',
        'email': 'bot@example.com',
        'phone': '',
        'category': 'question',
        'message': 'spam',
        'website': 'http://bot-filled-this.example.com',
    }

    def test_honeypot_trip_redirects_to_thank_you_silently(self):
        resp = self.client.post('/product/contact/', data=self.VALID_WITH_BOT)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/product/contact/thank-you/')

    def test_honeypot_trip_does_not_save_submission(self):
        self.client.post('/product/contact/', data=self.VALID_WITH_BOT)
        self.assertEqual(FeedbackSubmission.objects.count(), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.HoneypotTests -v 2`
Expected: the second test fails — a row was saved (the form is otherwise valid).

- [ ] **Step 3: Add the honeypot check**

In `server/views.py`, update the POST branch of `contact`:

```python
    if request.method == 'POST':
        form = ContactForm(data=request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if cd.get('website'):
                logger.info(
                    'contact honeypot tripped ip=%s user_agent=%r',
                    _client_ip(request),
                    request.META.get('HTTP_USER_AGENT', '')[:200],
                )
                return HttpResponseRedirect(reverse('product:contact-thank-you'))
            submission = models.FeedbackSubmission.objects.create(
                first_name=cd['first_name'],
                last_name=cd['last_name'],
                email=cd['email'],
                phone=cd['phone'],
                category=cd['category'],
                message=cd['message'],
                source_ip=_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
            logger.info(
                'contact submission saved id=%s category=%s email=%s',
                submission.pk, submission.category, _mask_email(submission.email),
            )
            return HttpResponseRedirect(reverse('product:contact-thank-you'))
    else:
        form = ContactForm()
    return render(request, 'server/contact.html', context={'form': form})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.HoneypotTests -v 2`
Expected: `Ran 2 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/views.py server/tests.py
git commit -m "Silently drop honeypot-tripped contact submissions"
```

---

## Task 12: Per-IP rate limiting

**Files:**
- Modify: `server/views.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
from datetime import timedelta
from django.utils import timezone


class RateLimitTests(TestCase):
    VALID = {
        'first_name': 'X',
        'last_name': 'Y',
        'email': 'x@example.com',
        'phone': '',
        'category': 'question',
        'message': 'hi',
        'website': '',
    }

    def setUp(self):
        self.ip = '203.0.113.99'
        self.settings_row = SiteSettings.get()
        self.settings_row.rate_limit_per_hour = 3
        self.settings_row.save()

    def _post(self):
        return self.client.post('/product/contact/', data=self.VALID, REMOTE_ADDR=self.ip)

    def test_under_limit_allowed(self):
        for _ in range(3):
            resp = self._post()
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(FeedbackSubmission.objects.count(), 3)

    def test_over_limit_blocked_and_not_saved(self):
        for _ in range(3):
            self._post()
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Too many submissions')
        self.assertEqual(FeedbackSubmission.objects.count(), 3)

    def test_limit_counts_only_last_hour(self):
        # Create 3 old rows (> 1 hour ago), shouldn't count
        for _ in range(3):
            row = FeedbackSubmission.objects.create(
                email='old@example.com', message='old',
                source_ip=self.ip,
            )
            FeedbackSubmission.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(hours=2)
            )
        resp = self._post()
        self.assertEqual(resp.status_code, 302)

    def test_zero_disables_rate_limit(self):
        self.settings_row.rate_limit_per_hour = 0
        self.settings_row.save()
        for _ in range(10):
            resp = self._post()
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(FeedbackSubmission.objects.count(), 10)

    def test_other_ip_not_rate_limited(self):
        for _ in range(3):
            self._post()
        # A different IP should still succeed
        resp = self.client.post(
            '/product/contact/', data=self.VALID, REMOTE_ADDR='203.0.113.100'
        )
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.RateLimitTests -v 2`
Expected: `test_over_limit_blocked_and_not_saved` fails — all 4 submissions succeed.

- [ ] **Step 3: Add rate-limit enforcement**

In `server/views.py`, update the POST branch of `contact`. Add a helper and integrate the check:

```python
from datetime import timedelta
from django.utils import timezone


def _rate_limit_exceeded(ip, limit):
    if not limit or not ip:
        return False
    since = timezone.now() - timedelta(hours=1)
    count = models.FeedbackSubmission.objects.filter(
        source_ip=ip, created_at__gte=since
    ).count()
    return count >= limit


def contact(request):
    if request.method == 'POST':
        form = ContactForm(data=request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if cd.get('website'):
                logger.info(
                    'contact honeypot tripped ip=%s user_agent=%r',
                    _client_ip(request),
                    request.META.get('HTTP_USER_AGENT', '')[:200],
                )
                return HttpResponseRedirect(reverse('product:contact-thank-you'))

            ip = _client_ip(request)
            settings_row = models.SiteSettings.get()
            if _rate_limit_exceeded(ip, settings_row.rate_limit_per_hour):
                logger.info('contact rate-limit tripped ip=%s', ip)
                form.add_error(None, 'Too many submissions — please try again later.')
                return render(request, 'server/contact.html', context={'form': form})

            submission = models.FeedbackSubmission.objects.create(
                first_name=cd['first_name'],
                last_name=cd['last_name'],
                email=cd['email'],
                phone=cd['phone'],
                category=cd['category'],
                message=cd['message'],
                source_ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
            logger.info(
                'contact submission saved id=%s category=%s email=%s',
                submission.pk, submission.category, _mask_email(submission.email),
            )
            return HttpResponseRedirect(reverse('product:contact-thank-you'))
    else:
        form = ContactForm()
    return render(request, 'server/contact.html', context={'form': form})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.RateLimitTests -v 2`
Expected: `Ran 5 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/views.py server/tests.py
git commit -m "Rate-limit contact submissions per IP"
```

---

## Task 13: Email delivery helper

**Files:**
- Modify: `server/feedback.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
from django.core import mail
from django.test import override_settings

from server.feedback import send_feedback_email


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendFeedbackEmailTests(TestCase):
    def setUp(self):
        self.submission = FeedbackSubmission.objects.create(
            first_name='Jane', last_name='Doe',
            email='jane@example.com', phone='+1-555-0100',
            category='bug', message='Found a bug',
        )

    def test_noop_when_to_blank(self):
        s = SiteSettings.get()
        s.feedback_email_to = ''
        s.feedback_email_from = 'noreply@example.com'
        s.save()
        send_feedback_email(self.submission, s)
        self.assertEqual(len(mail.outbox), 0)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.email_delivered_at)

    def test_noop_when_from_blank(self):
        s = SiteSettings.get()
        s.feedback_email_to = 'dest@example.com'
        s.feedback_email_from = ''
        s.save()
        send_feedback_email(self.submission, s)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_when_both_configured(self):
        s = SiteSettings.get()
        s.feedback_email_to = 'dest@example.com,dest2@example.com'
        s.feedback_email_from = 'noreply@example.com'
        s.save()
        send_feedback_email(self.submission, s)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['dest@example.com', 'dest2@example.com'])
        self.assertEqual(msg.from_email, 'noreply@example.com')
        self.assertIn('Bug report', msg.subject)
        self.assertIn('Jane', msg.subject)
        self.assertIn('Found a bug', msg.body)
        self.assertIn('jane@example.com', msg.body)
        self.submission.refresh_from_db()
        self.assertIsNotNone(self.submission.email_delivered_at)

    def test_failure_appends_delivery_note(self):
        s = SiteSettings.get()
        s.feedback_email_to = 'dest@example.com'
        s.feedback_email_from = 'noreply@example.com'
        s.save()
        from unittest.mock import patch
        with patch('server.feedback.send_mail', side_effect=Exception('SMTP down')):
            send_feedback_email(self.submission, s)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.email_delivered_at)
        self.assertIn('SMTP down', self.submission.delivery_notes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.SendFeedbackEmailTests -v 2`
Expected: ImportError — `send_feedback_email` does not exist.

- [ ] **Step 3: Add the helper**

Append to `server/feedback.py`:

```python
import logging

from django.core.mail import send_mail
from django.utils import timezone


logger = logging.getLogger(__name__)


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.SendFeedbackEmailTests -v 2`
Expected: `Ran 4 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/feedback.py server/tests.py
git commit -m "Add send_feedback_email delivery helper"
```

---

## Task 14: Workato webhook helper

**Files:**
- Modify: `server/feedback.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `server/tests.py`:

```python
import json
from unittest.mock import patch, MagicMock

from server.feedback import post_to_workato


class PostToWorkatoTests(TestCase):
    def setUp(self):
        self.submission = FeedbackSubmission.objects.create(
            first_name='Jane', last_name='Doe',
            email='jane@example.com', phone='+1-555',
            category='bug', message='m',
        )

    def test_noop_when_url_blank(self):
        s = SiteSettings.get()
        s.workato_webhook_url = ''
        s.save()
        with patch('server.feedback.urllib.request.urlopen') as u:
            post_to_workato(self.submission, s)
            u.assert_not_called()

    def test_posts_json_payload_on_configured_url(self):
        s = SiteSettings.get()
        s.workato_webhook_url = 'https://hooks.example.com/r/123'
        s.save()

        fake_response = MagicMock()
        fake_response.__enter__.return_value.status = 200
        with patch('server.feedback.urllib.request.urlopen',
                   return_value=fake_response) as u:
            post_to_workato(self.submission, s)
            u.assert_called_once()
            req = u.call_args[0][0]
            self.assertEqual(req.full_url, 'https://hooks.example.com/r/123')
            self.assertEqual(req.get_method(), 'POST')
            self.assertEqual(req.headers['Content-type'], 'application/json')
            payload = json.loads(req.data)
            self.assertEqual(payload['email'], 'jane@example.com')
            self.assertEqual(payload['category'], 'bug')
            self.assertEqual(payload['category_label'], 'Bug report')
            self.assertEqual(payload['source'], 'product-registry')
            self.assertEqual(payload['submission_id'], self.submission.pk)

        self.submission.refresh_from_db()
        self.assertIsNotNone(self.submission.webhook_delivered_at)

    def test_failure_appends_delivery_note(self):
        s = SiteSettings.get()
        s.workato_webhook_url = 'https://hooks.example.com/r/123'
        s.save()
        with patch('server.feedback.urllib.request.urlopen',
                   side_effect=Exception('timeout')):
            post_to_workato(self.submission, s)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.webhook_delivered_at)
        self.assertIn('timeout', self.submission.delivery_notes)

    def test_non_2xx_status_recorded_as_failure(self):
        s = SiteSettings.get()
        s.workato_webhook_url = 'https://hooks.example.com/r/123'
        s.save()
        fake_response = MagicMock()
        fake_response.__enter__.return_value.status = 500
        with patch('server.feedback.urllib.request.urlopen',
                   return_value=fake_response):
            post_to_workato(self.submission, s)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.webhook_delivered_at)
        self.assertIn('500', self.submission.delivery_notes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.PostToWorkatoTests -v 2`
Expected: ImportError — `post_to_workato` does not exist.

- [ ] **Step 3: Add the helper**

Append to `server/feedback.py`:

```python
import json
import urllib.request


WORKATO_CONNECT_TIMEOUT = 5
WORKATO_READ_TIMEOUT = 10


def post_to_workato(submission, settings_row):
    """POST the submission as JSON to Workato webhook. Best-effort.

    Stamps webhook_delivered_at on 2xx, appends to delivery_notes on failure.
    Never raises.
    """
    url = (settings_row.workato_webhook_url or '').strip()
    if not url:
        return

    payload = {
        'submitted_at': submission.created_at.isoformat(),
        'first_name': submission.first_name,
        'last_name': submission.last_name,
        'email': submission.email,
        'phone': submission.phone,
        'category': submission.category,
        'category_label': submission.get_category_display(),
        'message': submission.message,
        'source': 'product-registry',
        'submission_id': submission.pk,
    }
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={'Content-type': 'application/json'},
    )

    try:
        with urllib.request.urlopen(
            req, timeout=WORKATO_READ_TIMEOUT,
        ) as response:
            status = response.status
            if 200 <= status < 300:
                submission.webhook_delivered_at = timezone.now()
                submission.save(update_fields=['webhook_delivered_at'])
            else:
                logger.warning('Workato webhook returned %s for submission %s',
                               status, submission.pk)
                _append_note(submission, f'webhook failed: HTTP {status}')
    except Exception as exc:
        logger.warning('Workato webhook call failed for submission %s: %s',
                       submission.pk, exc)
        _append_note(submission, f'webhook failed: {exc}')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.PostToWorkatoTests -v 2`
Expected: `Ran 4 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add server/feedback.py server/tests.py
git commit -m "Add post_to_workato delivery helper"
```

---

## Task 15: Wire delivery into the contact view

**Files:**
- Modify: `server/views.py`
- Modify: `server/tests.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `server/tests.py`:

```python
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ContactEndToEndDeliveryTests(TestCase):
    VALID = {
        'first_name': 'Jane',
        'last_name': 'Doe',
        'email': 'jane@example.com',
        'phone': '+1-555',
        'category': 'bug',
        'message': 'msg',
        'website': '',
    }

    def setUp(self):
        s = SiteSettings.get()
        s.feedback_email_to = 'dest@example.com'
        s.feedback_email_from = 'noreply@example.com'
        s.workato_webhook_url = 'https://hooks.example.com/r/abc'
        s.save()

    def test_post_fires_email_and_webhook(self):
        fake_response = MagicMock()
        fake_response.__enter__.return_value.status = 200
        with patch('server.feedback.urllib.request.urlopen',
                   return_value=fake_response) as u:
            resp = self.client.post('/product/contact/', data=self.VALID)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        u.assert_called_once()
        row = FeedbackSubmission.objects.get()
        self.assertIsNotNone(row.email_delivered_at)
        self.assertIsNotNone(row.webhook_delivered_at)

    def test_webhook_failure_does_not_break_email(self):
        with patch('server.feedback.urllib.request.urlopen',
                   side_effect=Exception('net down')):
            resp = self.client.post('/product/contact/', data=self.VALID)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        row = FeedbackSubmission.objects.get()
        self.assertIsNotNone(row.email_delivered_at)
        self.assertIsNone(row.webhook_delivered_at)

    def test_email_failure_does_not_break_webhook(self):
        fake_response = MagicMock()
        fake_response.__enter__.return_value.status = 200
        with patch('server.feedback.send_mail', side_effect=Exception('smtp down')), \
             patch('server.feedback.urllib.request.urlopen',
                   return_value=fake_response):
            resp = self.client.post('/product/contact/', data=self.VALID)
        self.assertEqual(resp.status_code, 302)
        row = FeedbackSubmission.objects.get()
        self.assertIsNone(row.email_delivered_at)
        self.assertIsNotNone(row.webhook_delivered_at)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test server.tests.ContactEndToEndDeliveryTests -v 2`
Expected: no email sent, no webhook called — the view doesn't invoke the helpers yet.

- [ ] **Step 3: Wire helpers into the view**

In `server/views.py`, update the `contact` view's POST branch to call both helpers after saving:

```python
from server.feedback import ContactForm, send_feedback_email, post_to_workato


def contact(request):
    if request.method == 'POST':
        form = ContactForm(data=request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if cd.get('website'):
                logger.info(
                    'contact honeypot tripped ip=%s user_agent=%r',
                    _client_ip(request),
                    request.META.get('HTTP_USER_AGENT', '')[:200],
                )
                return HttpResponseRedirect(reverse('product:contact-thank-you'))

            ip = _client_ip(request)
            settings_row = models.SiteSettings.get()
            if _rate_limit_exceeded(ip, settings_row.rate_limit_per_hour):
                logger.info('contact rate-limit tripped ip=%s', ip)
                form.add_error(None, 'Too many submissions — please try again later.')
                return render(request, 'server/contact.html', context={'form': form})

            submission = models.FeedbackSubmission.objects.create(
                first_name=cd['first_name'],
                last_name=cd['last_name'],
                email=cd['email'],
                phone=cd['phone'],
                category=cd['category'],
                message=cd['message'],
                source_ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
            logger.info(
                'contact submission saved id=%s category=%s email=%s',
                submission.pk, submission.category, _mask_email(submission.email),
            )

            send_feedback_email(submission, settings_row)
            post_to_workato(submission, settings_row)

            return HttpResponseRedirect(reverse('product:contact-thank-you'))
    else:
        form = ContactForm()
    return render(request, 'server/contact.html', context={'form': form})
```

Replace the earlier single import `from server.feedback import ContactForm` with the expanded import above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test server.tests.ContactEndToEndDeliveryTests -v 2`
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 5: Run the full test suite**

Run: `uv run python manage.py test server -v 2`
Expected: all tests added so far pass. Note any failure — fix it before moving on.

- [ ] **Step 6: Commit**

```bash
git add server/views.py server/tests.py
git commit -m "Dispatch email and webhook on contact form submission"
```

---

## Task 16: Email backend configuration

**Files:**
- Modify: `product_registry/settings.py`

- [ ] **Step 1: Add env-driven email backend settings**

Append to `product_registry/settings.py`:

```python
# Email
# In dev (no EMAIL_HOST), Django falls back to printing emails to the console.
# In prod, set EMAIL_HOST/EMAIL_PORT/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD env
# vars to point at AWS SES SMTP. See:
# https://docs.aws.amazon.com/ses/latest/dg/send-email-smtp.html
if os.environ.get('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ['EMAIL_HOST']
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', '1') == '1'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

- [ ] **Step 2: Verify tests still pass**

Run: `uv run python manage.py test server -v 2`
Expected: all tests pass (tests use `override_settings` so this change doesn't affect them).

- [ ] **Step 3: Commit**

```bash
git add product_registry/settings.py
git commit -m "Configure email backend via env vars (console backend fallback)"
```

---

## Task 17: Exclude new tables from data-reload SQL

**Files:**
- Modify: `load_local_db_to_remote_db.sql`

- [ ] **Step 1: Add exclusion note**

Open `load_local_db_to_remote_db.sql`. Replace its current content:

```sql
begin transaction;
-- NOTE: server_feedbacksubmission and server_sitesettings are intentionally
-- NOT copied from local → prod. Both are prod-only:
--   * server_sitesettings holds admin-editable production config
--     (feedback email recipients, Workato webhook URL). Copying from local
--     would wipe prod config.
--   * server_feedbacksubmission holds real user submissions; local is test data.
insert into rds.server_product select * from lds.server_product;
insert into rds.server_dimension select * from lds.server_dimension;
insert into rds.server_prodbattery select * from lds.server_prodbattery;
insert into rds.server_dcinput select * from lds.server_dcinput;
insert into rds.server_dcoutput select * from lds.server_dcoutput;
insert into rds.server_entity select * from lds.server_entity;
insert into rds.server_certificationagency select * from lds.server_certificationagency;
insert into rds.server_prodcertification select * from lds.server_prodcertification;
insert into rds.server_checksum select * from lds.server_checksum;
insert into rds.server_firmware select * from lds.server_firmware;
insert into rds.server_prodcell select * from lds.server_prodcell;
insert into rds.server_prodglazing select * from lds.server_prodglazing;
insert into rds.server_moduleelectrating select * from lds.server_moduleelectrating;
insert into rds.server_prodmodule select * from lds.server_prodmodule;
insert into rds.server_sourcecountry select * from lds.server_sourcecountry;
insert into rds.server_productalternativeidentifier select * from lds.server_productalternativeidentifier;
insert into rds.server_entityalternativeidentifier select * from lds.server_entityalternativeidentifier;
insert into rds.server_paymentmethodalternativeidentifier select * from lds.server_paymentmethodalternativeidentifier;
--commit;
```

Only change: the block comment between `begin transaction;` and the first `insert`.

- [ ] **Step 2: Commit**

```bash
git add load_local_db_to_remote_db.sql
git commit -m "Note that feedback/settings tables are excluded from data reload"
```

---

## Task 18: Final verification

- [ ] **Step 1: Run the complete test suite**

Run: `uv run python manage.py test server -v 2`
Expected: every test passes, no errors, no warnings about unapplied migrations.

- [ ] **Step 2: Apply migrations on the dev SQLite DB**

Run: `uv run python manage.py migrate`
Expected: two new migrations applied (FeedbackSubmission + SiteSettings).

- [ ] **Step 3: Create a superuser for manual testing**

Run: `uv run python manage.py createsuperuser`
(Pick any username / email / password for local use.)

- [ ] **Step 4: Start the server and walk the golden path manually**

Run: `uv run python manage.py runserver`

Walkthrough:
1. Visit `http://127.0.0.1:8000/product/` — orange "Contact Us" button in the top-right of the navbar.
2. Click it — form page loads at `/product/contact/`, heading "Get in touch".
3. Submit the form with required fields empty — see inline errors.
4. Submit a valid form — lands on `/product/contact/thank-you/` with success alert.
5. Refresh the thank-you page — no form resubmission warning.
6. Visit `/admin/` — log in with the superuser.
7. Under "SERVER" > "Feedback submissions", see the row. Fields read-only, no "Add" button.
8. Under "SERVER" > "Site settings", fill in `feedback_email_to` and `feedback_email_from` with any values. Save.
9. Submit another form. Because the dev email backend is console, the email body is printed in the terminal running `runserver`.
10. Set `rate_limit_per_hour` to 1 in admin. Submit two forms — second should show "Too many submissions".
11. In the form, use browser devtools to reveal the hidden honeypot input (`website`), enter a value, submit. Redirects to thank-you but no new DB row is created.

Stop the server (Ctrl+C).

- [ ] **Step 5: Verify no unintended files changed**

Run: `git status`
Expected: working tree is clean.

- [ ] **Step 6: Push the branch**

```bash
git push
```

The ECS deployment flow is out of scope for this plan; follow the standard deploy script once the branch is merged.

---

## Done — what shipped

- `FeedbackSubmission` table with category, contact info, message, source IP/UA, per-destination delivery timestamps, delivery-failure notes.
- `SiteSettings` singleton table editable in Django admin: email to/from, Workato webhook URL, per-IP rate limit.
- `/product/contact/` form page and `/product/contact/thank-you/` confirmation.
- "Contact Us" button in the navbar on every page of the site.
- Honeypot field + per-IP rate limit (DB-backed, no external deps).
- Best-effort email via Django `send_mail` (SES SMTP in prod, console in dev).
- Best-effort JSON POST to the Workato webhook URL.
- Failures in either destination don't affect the other and don't fail the user-facing request.
- `load_local_db_to_remote_db.sql` updated with the exclusion note so data reloads don't clobber prod config or submissions.
