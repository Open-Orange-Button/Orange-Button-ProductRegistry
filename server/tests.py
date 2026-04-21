from django.test import TestCase


class SmokeTests(TestCase):
    def test_runner_works(self):
        self.assertEqual(1 + 1, 2)
