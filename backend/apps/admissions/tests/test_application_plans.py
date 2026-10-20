from unittest.mock import patch

from rest_framework.test import APITestCase

from ..models import Application, ApplicationStatusHistory, Essay, University
from ..serializers.records import ApplicationSerializer
from ..test_audit_base import AuditBaseMixin


class ApplicationPlanTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.university = University.objects.create(name='Riverstone University', country='Testland')
        self.application = Application.objects.create(student=self.student, university=self.university,
                                                      program='Computer Science', status='shortlisted')
        self.url = f'/api/applications/{self.application.pk}/'
        self.client.force_authenticate(self.student_user)

    def test_plan_save_is_separate_from_submission_and_history_is_not_duplicated(self):
        saved = self.client.patch(self.url, {'deadline': '2027-01-01', 'application_portal_url': 'https://apply.university.test/'}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['status'], 'shortlisted')
        self.assertFalse(ApplicationStatusHistory.objects.filter(application=self.application).exists())
        submitted = self.client.patch(self.url, {'status': 'submitted'}, format='json')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertEqual(len(submitted.data['status_history']), 1)
        repeated = self.client.patch(self.url, {'status': 'submitted'}, format='json')
        self.assertEqual(len(repeated.data['status_history']), 1)

    def test_student_can_link_own_essay_to_own_application_only(self):
        essay = Essay.objects.create(student=self.student, title='My statement')
        result = self.client.patch(f'/api/essays/{essay.pk}/', {'application': self.application.pk}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        other = Application.objects.create(student=self.student_b, university=self.university, program='Computer Science')
        result = self.client.patch(f'/api/essays/{essay.pk}/', {'application': other.pk}, format='json')
        self.assertEqual(result.status_code, 400)
        essay.refresh_from_db()
        self.assertEqual(essay.application_id, self.application.pk)

    def test_student_cannot_erase_a_counselor_decision_but_can_save_notes(self):
        Application.objects.filter(pk=self.application.pk).update(status='accepted')
        self.assertEqual(self.client.patch(self.url, {'status': 'applying'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(self.url, {'notes': 'Waiting for the offer letter'}, format='json').status_code, 200)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.patch(self.url, {'status': 'waitlisted'}, format='json').status_code, 200)

    def test_decision_committed_after_validation_is_rechecked_before_save(self):
        original = ApplicationSerializer.validate_status
        first = True

        def validate(serializer, value):
            nonlocal first
            result = original(serializer, value)
            if first:
                first = False
                Application.objects.filter(pk=self.application.pk).update(status='accepted')
            return result

        with patch.object(ApplicationSerializer, 'validate_status', validate):
            result = self.client.patch(self.url, {'status': 'applying'}, format='json')
        self.assertEqual(result.status_code, 400)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'accepted')
