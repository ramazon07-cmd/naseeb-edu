"""An application with a decision was submitted: it stays counted as submitted."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Application, Notification, RecommendationLetter, University
from apps.admissions.test_audit_base import AuditBaseMixin


class DecidedApplicationTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.university = University.objects.create(name='Decision U', country='USA')
        self.application = Application.objects.create(
            student=self.student, university=self.university, program='CS', status='submitted',
            deadline=timezone.localdate() + timedelta(days=5),
        )

    def numbers(self):
        self.client.force_authenticate(self.counselor)
        stats = self.client.get('/api/dashboard/stats/').data
        profile = self.client.get(f'/api/students/{self.student.id}/').data
        return profile['progress_percent'], stats['applications_submitted']

    def test_a_decision_keeps_the_application_submitted(self):
        self.assertEqual(self.numbers(), (100, 1))
        for decision in ('waitlisted', 'rejected', 'accepted'):
            response = self.client.patch(f'/api/applications/{self.application.id}/', {'status': decision},
                                         format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(self.numbers(), (100, 1), decision)

    def test_no_deadline_reminder_after_a_decision(self):
        self.application.status = 'waitlisted'
        self.application.save()
        call_command('generate_notifications', stdout=StringIO())
        self.assertFalse(Notification.objects.filter(student=self.student).exists())
        self.application.status = 'applying'
        self.application.save()
        call_command('generate_notifications', stdout=StringIO())
        self.assertTrue(Notification.objects.filter(student=self.student).exists())


class ReadinessTests(AuditBaseMixin, APITestCase):
    def profile(self):
        self.client.force_authenticate(self.counselor)
        data = self.client.get(f'/api/students/{self.student.id}/').data
        return data['progress_percent'], data['readiness_items_done'], data['readiness_items_total']

    def test_letters_count_once_the_recommender_sends_them(self):
        self.assertEqual(self.profile(), (0, 0, 0))
        letter = RecommendationLetter.objects.create(student=self.student, recommender_name='Mr Aliyev')
        self.assertEqual(self.profile(), (0, 0, 1))
        for status_value, expected in (('drafting', (0, 0, 1)), ('submitted', (100, 1, 1)), ('approved', (100, 1, 1))):
            response = self.client.patch(f'/api/recommendations/{letter.id}/', {'status': status_value}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(self.profile(), expected, status_value)
