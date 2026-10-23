"""Assigned work is submitted by students and controlled by its reviewer."""
from datetime import date
from types import SimpleNamespace

from rest_framework.exceptions import ValidationError

from ..models import Task, XPTransaction
from ..serializers.records import TaskSerializer
from ..views.records import TaskViewSet
from .base import RoleIsolationBase


class TaskOwnershipTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            student=self.student_a, assigned_by=self.counselor,
            title='Counselor assignment', due_date=date(2027, 12, 1),
        )
        self.url = f'/api/tasks/{self.task.pk}/'
        self.client.force_authenticate(self.student_a_user)

    def test_student_cannot_set_assigned_work_status_or_change_instructions(self):
        for value in ('todo', 'in_progress', 'approved', 'late'):
            with self.subTest(status=value):
                response = self.client.patch(self.url, {'status': value}, format='json')
                self.assertEqual(response.status_code, 400, response.data)
        for values in ({'title': 'Replaced'}, {'description': 'Changed'},
                       {'due_date': '2030-01-01'}, {'priority': 'low'}):
            self.assertEqual(self.client.patch(self.url, values, format='json').status_code, 400)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)
        self.assertEqual(self.task.title, 'Counselor assignment')

    def test_empty_submission_cannot_change_status_or_award_xp(self):
        for values in ({'status': 'submitted'}, {'student_response': '   '},
                       {'student_response': '', 'submission_url': ''}):
            response = self.client.patch(self.url, values, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)
        self.assertIsNone(self.task.submitted_at)
        self.assertFalse(XPTransaction.objects.exists())

    def test_response_submits_automatically_and_waits_for_reviewer(self):
        response = self.client.patch(self.url, {'student_response': 'Here is my work.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertIsNotNone(response.data['submitted_at'])
        for values in ({'status': 'todo'}, {'student_response': 'Replaced after submitting'}):
            self.assertEqual(self.client.patch(self.url, values, format='json').status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.student_response, 'Here is my work.')
        self.assertEqual(self.task.status, Task.Status.SUBMITTED)
        self.client.force_authenticate(self.counselor)
        response = self.client.post(self.url + 'send-back/', {'note': 'Add a source.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.student_a_user)
        response = self.client.patch(self.url, {'student_response': 'Updated with sources.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(self.url + 'approve/', {}, format='json').status_code, 200)
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.patch(self.url, {'student_response': 'Changed'}, format='json').status_code, 400)

    def test_submission_link_alone_is_accepted(self):
        response = self.client.patch(self.url, {'submission_url': 'https://example.com/my-work'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')

    def test_stale_student_save_cannot_overwrite_a_new_review_state(self):
        request = SimpleNamespace(user=self.student_a_user)
        view = TaskViewSet()
        view.request = request
        for status in (Task.Status.SUBMITTED, Task.Status.APPROVED):
            Task.objects.filter(pk=self.task.pk).update(status=Task.Status.TODO)
            self.task.refresh_from_db()
            serializer = TaskSerializer(self.task, data={'student_response': 'Stale response'},
                                        partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            # A reviewer or another submission finishes after validation but before save.
            Task.objects.filter(pk=self.task.pk).update(status=status)
            with self.assertRaises(ValidationError):
                view.perform_update(serializer)
            self.task.refresh_from_db()
            self.assertEqual(self.task.status, status)
            self.assertEqual(self.task.student_response, '')

    def test_personal_tasks_are_managed_independently_and_filter_separately(self):
        response = self.client.post('/api/tasks/', {
            'student': self.student_a.pk, 'title': 'My study plan', 'due_date': '2027-12-02',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        personal_id = response.data['id']
        self.assertTrue(response.data['is_self_assigned'])
        updated = self.client.patch(f'/api/tasks/{personal_id}/', {
            'title': 'My updated plan', 'status': 'in_progress',
        }, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['xp_reward'], 0)
        assigned = self.results(self.client.get('/api/tasks/?self_assigned=false'))
        personal = self.results(self.client.get('/api/tasks/?self_assigned=true'))
        self.assertEqual([row['id'] for row in assigned], [self.task.pk])
        self.assertEqual([row['id'] for row in personal], [personal_id])
        self.assertEqual(self.client.delete(f'/api/tasks/{personal_id}/').status_code, 204)

    def test_every_task_priority_can_be_approved_without_creating_xp(self):
        self.client.force_authenticate(self.counselor)
        for priority in Task.Priority.values:
            with self.subTest(priority=priority):
                task = Task.objects.create(student=self.student_a, assigned_by=self.counselor,
                                           title=f'{priority} task', priority=priority,
                                           due_date=date(2027, 12, 1), status='submitted', student_response='Done.')
                for _ in range(2):
                    response = self.client.post(f'/api/tasks/{task.pk}/approve/', {}, format='json')
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertEqual(response.data['status'], 'approved')
                    self.assertEqual(response.data['xp_awarded'], 0)
                    self.assertEqual(response.data['xp_reward'], 0)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.xp_total, 0)
        self.assertFalse(XPTransaction.objects.filter(student=self.student_a).exists())
