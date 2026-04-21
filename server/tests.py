from django.test import TestCase

from server.models import FeedbackSubmission


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
