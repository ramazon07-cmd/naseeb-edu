"""Late means the student still owes the work after its due date."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Document, Notification, RoadmapMission, Task
from apps.admissions.test_audit_base import AuditBaseMixin


class SubmittedWorkIsNotLateTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.yesterday = timezone.localdate() - timedelta(days=1)

    def numbers(self):
        self.client.force_authenticate(self.counselor)
        profile = self.client.get(f'/api/students/{self.student.id}/').data
        stats = self.client.get('/api/dashboard/stats/').data
        return profile['is_at_risk'], stats['students_at_risk'], stats['tasks_late']

    def test_submitted_task_past_due_is_waiting_on_the_reviewer(self):
        task = Task.objects.create(student=self.student, title='Essay', due_date=self.yesterday,
                                   status=Task.Status.SUBMITTED)
        self.assertEqual(self.numbers(), (False, 0, 0))
        self.assertFalse(self.client.get(f'/api/tasks/{task.id}/').data['is_overdue'])
        call_command('generate_notifications', stdout=StringIO())
        self.assertFalse(Notification.objects.filter(student=self.student).exists())

        # Sent back for changes: the student owes it again, and it is late.
        self.client.patch(f'/api/tasks/{task.id}/', {'status': 'in_progress'}, format='json')
        self.assertEqual(self.numbers(), (True, 1, 1))
        self.assertTrue(self.client.get(f'/api/tasks/{task.id}/').data['is_overdue'])

    def test_late_status_counts_only_once_the_due_date_has_passed(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        task = Task.objects.create(student=self.student, title='Essay', due_date=tomorrow, status=Task.Status.LATE)
        # Every late number agrees: owed and past due, not the status alone.
        self.assertEqual(self.numbers(), (False, 0, 0))
        self.assertFalse(self.client.get(f'/api/tasks/{task.id}/').data['is_overdue'])
        task.due_date = self.yesterday
        task.save()
        self.assertEqual(self.numbers(), (True, 1, 1))

    def test_submitted_mission_past_due_is_not_at_risk(self):
        RoadmapMission.objects.create(student=self.student, title='Shortlist', due_date=self.yesterday,
                                      status=RoadmapMission.Status.SUBMITTED)
        self.assertEqual(self.numbers()[:2], (False, 0))
        RoadmapMission.objects.create(student=self.student, title='Profile', due_date=self.yesterday)
        self.assertEqual(self.numbers()[:2], (True, 1))


class NotificationFollowsTheWorkTests(AuditBaseMixin, APITestCase):
    def run_job(self):
        call_command('generate_notifications', stdout=StringIO())
        return {n.title: (n.message, n.is_read) for n in Notification.objects.filter(student=self.student)}

    def test_resolved_alerts_stop_showing_as_unread(self):
        task = Task.objects.create(student=self.student, title='Essay', status=Task.Status.TODO,
                                   due_date=timezone.localdate() - timedelta(days=2))
        self.assertEqual(self.run_job()['Late tasks require attention'][1], False)
        task.status = Task.Status.SUBMITTED
        task.save()
        self.assertEqual(self.run_job()['Late tasks require attention'][1], True)

    def test_a_rejected_document_still_needs_an_upload(self):
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REJECTED,
                                google_docs_url='https://docs.google.com/document/d/x/edit')
        self.assertIn('Required documents are missing', self.run_job())


class OpenTaskFilterTests(AuditBaseMixin, APITestCase):
    def test_open_filter_lists_only_work_still_owed(self):
        today = timezone.localdate()
        for index, status_value in enumerate(Task.Status.values):
            Task.objects.create(student=self.student, title=status_value, status=status_value,
                                due_date=today + timedelta(days=index))
        self.client.force_authenticate(self.counselor)
        rows = self.client.get('/api/tasks/?open=true&ordering=due').data['results']
        self.assertEqual([row['status'] for row in rows], ['todo', 'in_progress', 'late'])
        rows = self.client.get('/api/tasks/?open=false').data['results']
        self.assertEqual({row['status'] for row in rows}, {'submitted', 'approved'})
        self.assertEqual(self.client.get('/api/tasks/?open=maybe').status_code, 400)
