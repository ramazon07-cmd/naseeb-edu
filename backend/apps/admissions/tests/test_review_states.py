"""Reviewer decisions (approved / verified) belong to staff.

A student can resubmit work, but cannot quietly undo a reviewer's decision
and so change the numbers derived from it.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Activity, Achievement, Document, Honor, RecommendationLetter, Task
from apps.admissions.test_audit_base import AuditBaseMixin


class ApprovedTaskTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            student=self.student, assigned_by=self.counselor, title='Essay outline',
            due_date=timezone.localdate() + timedelta(days=3), status=Task.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/approve/').status_code, 200)

    def test_student_cannot_reopen_an_approved_task(self):
        self.client.force_authenticate(self.student_user)
        for status_value in ('todo', 'in_progress', 'submitted'):
            response = self.client.patch(f'/api/tasks/{self.task.id}/', {'status': status_value}, format='json')
            self.assertEqual(response.status_code, 400, status_value)
        response = self.client.patch(f'/api/tasks/{self.task.id}/', {'student_response': 'edited'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.APPROVED)
        profile = self.client.get(f'/api/students/{self.student.id}/').data
        self.assertEqual(profile['task_progress_percent'], 100)

    def test_reviewer_can_still_reopen_an_approved_task(self):
        response = self.client.patch(f'/api/tasks/{self.task.id}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(response.status_code, 200)


class ReviewedDocumentTests(AuditBaseMixin, APITestCase):
    def test_student_cannot_pull_a_reviewed_document_back_without_new_work(self):
        for current in ('reviewing', 'approved'):
            document = Document.objects.create(
                student=self.student, title=f'Transcript {current}', status=current,
                google_docs_url='https://docs.google.com/document/d/abc/edit',
            )
            self.client.force_authenticate(self.student_user)
            response = self.client.patch(f'/api/documents/{document.id}/', {'status': 'uploaded'}, format='json')
            self.assertEqual(response.status_code, 400, current)
            document.refresh_from_db()
            self.assertEqual(document.status, current)
            # New work does resubmit it.
            response = self.client.patch(
                f'/api/documents/{document.id}/',
                {'google_docs_url': 'https://docs.google.com/document/d/new/edit'}, format='json',
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['status'], 'uploaded')

    def test_renaming_a_link_document_keeps_it_in_review(self):
        link = 'https://docs.google.com/document/d/abc/edit'
        document = Document.objects.create(
            student=self.student, title='Transcript', status='reviewing', google_docs_url=link,
        )
        self.client.force_authenticate(self.student_user)
        response = self.client.patch(
            f'/api/documents/{document.id}/', {'title': 'Final transcript', 'google_docs_url': link}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        document.refresh_from_db()
        self.assertEqual((document.title, document.status), ('Final transcript', 'reviewing'))

    def test_student_can_resubmit_a_rejected_document(self):
        document = Document.objects.create(
            student=self.student, title='Passport', status='rejected',
            google_docs_url='https://docs.google.com/document/d/abc/edit',
        )
        self.client.force_authenticate(self.student_user)
        response = self.client.patch(f'/api/documents/{document.id}/', {'status': 'uploaded'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)


class ApprovedRecommendationTests(AuditBaseMixin, APITestCase):
    def test_student_cannot_reopen_an_approved_letter(self):
        letter = RecommendationLetter.objects.create(
            student=self.student, recommender_name='Ms Karimova', status='approved',
        )
        self.client.force_authenticate(self.student_user)
        response = self.client.patch(f'/api/recommendations/{letter.id}/', {'status': 'drafting'}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/recommendations/{letter.id}/', {'notes': 'thank-you sent'}, format='json')
        self.assertEqual(response.status_code, 200)
        letter.refresh_from_db()
        self.assertEqual(letter.status, 'approved')


class VerifiedRecordTests(AuditBaseMixin, APITestCase):
    def records(self):
        return {
            'activities': Activity.objects.create(student=self.student, name='Robotics club', verified=True),
            'honors': Honor.objects.create(student=self.student, title='Olympiad bronze', verified=True),
            'achievements': Achievement.objects.create(
                student=self.student, title='App launch', category='project', description='Built it', verified=True,
            ),
        }

    def test_student_edit_sends_a_verified_record_back_for_review(self):
        edits = {'activities': {'role': 'President'}, 'honors': {'level': 'national'},
                 'achievements': {'impact': '10,000 users'}}
        self.client.force_authenticate(self.student_user)
        for resource, record in self.records().items():
            response = self.client.patch(f'/api/{resource}/{record.id}/', edits[resource], format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertFalse(response.data['verified'], resource)
            record.refresh_from_db()
            self.assertFalse(record.verified, resource)

    def test_unchanged_save_and_counselor_edit_keep_the_badge(self):
        records = self.records()
        self.client.force_authenticate(self.student_user)
        response = self.client.patch(f'/api/activities/{records["activities"].id}/', {'name': 'Robotics club'},
                                     format='json')
        self.assertTrue(response.data['verified'])
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/honors/{records["honors"].id}/', {'issuer': 'Ministry'}, format='json')
        self.assertTrue(response.data['verified'])
