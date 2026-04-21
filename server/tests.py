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
