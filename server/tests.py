from django.contrib.auth import get_user_model
from django.test import TestCase

from server.models import FeedbackSubmission, SiteSettings


class SmokeTests(TestCase):
    def test_runner_works(self):
        self.assertEqual(1 + 1, 2)


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


class ContactThankYouViewTests(TestCase):
    def test_reverses_to_url(self):
        self.assertEqual(reverse('product:contact-thank-you'), '/product/contact/thank-you/')

    def test_returns_200_with_success_message(self):
        resp = self.client.get('/product/contact/thank-you/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Thanks, we got your message')


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
