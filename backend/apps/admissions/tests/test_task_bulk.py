"""POST /api/tasks/bulk/: one task for many students, all in scope or none."""
import math
from unittest import mock

from django.db import connection
from django.db.models import fields as model_fields
from django.test.utils import CaptureQueriesContext

from apps.users.models import User

from ..models import ActivityLog, Notification, StudentProfile, Task
from ..views.records import BULK_TASK_LIMIT
from .base import RoleIsolationBase

URL = '/api/tasks/bulk/'


class BulkTaskTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)

    def add_student(self, counselor=None, school=None):
        school = school or self.school_a
        number = User.objects.count()
        user = User.objects.create_user(
            username=f'bulk-{number}', email=f'bulk-{number}@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=school,
        )
        return StudentProfile.objects.create(user=user, school=school, assigned_counselor=counselor or self.counselor)

    def payload(self, students, **extra):
        return {'students': students, 'title': 'Draft essay', 'description': 'First pass', 'due_date': '2030-05-01', 'priority': 'high', **extra}

    def test_creates_one_task_per_student(self):
        other = self.add_student()
        response = self.client.post(URL, self.payload([self.student_a.pk, other.pk, other.pk]), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['created'], 2)
        tasks = Task.objects.filter(pk__in=response.data['ids'])
        self.assertEqual({task.student_id for task in tasks}, {self.student_a.pk, other.pk})
        for task in tasks:
            self.assertEqual((task.title, task.description, str(task.due_date), task.priority), ('Draft essay', 'First pass', '2030-05-01', 'high'))
            self.assertEqual(task.assigned_by, self.counselor)
            self.assertFalse(task.is_self_assigned)
            self.assertEqual(task.status, Task.Status.TODO)
            self.assertIsNotNone(task.created_at)
        # Same side effects as a single create: no log row, no notice.
        self.assertEqual(ActivityLog.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_progress_cache_is_dropped_after_commit(self):
        with mock.patch('apps.admissions.views.records.invalidate_progress_summary') as invalidate:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.assertEqual(self.client.post(URL, self.payload([self.student_a.pk]), format='json').status_code, 201)
            invalidate.assert_not_called()
            for callback in callbacks:
                callback()
            invalidate.assert_called_once_with()

    def test_validates_fields_like_a_single_create(self):
        response = self.client.post(URL, self.payload([self.student_a.pk], priority='whenever', due_date=''), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('priority', response.data)
        self.assertIn('due_date', response.data)
        response = self.client.post(URL, self.payload([self.student_a.pk], status='approved'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_cross_school_student_rejects_the_whole_request(self):
        response = self.client.post(URL, self.payload([self.student_a.pk, self.student_b.pk]), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('students', response.data)
        self.assertFalse(Task.objects.exists())

    def test_another_counselors_student_rejects_the_whole_request(self):
        colleague = User.objects.create_user(
            username='colleague', email='colleague@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school_a,
        )
        theirs = self.add_student(counselor=colleague)
        response = self.client.post(URL, self.payload([self.student_a.pk, theirs.pk]), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_unknown_id_rejects_the_whole_request(self):
        response = self.client.post(URL, self.payload([self.student_a.pk, 999999]), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_student_and_organization_cannot_bulk_assign(self):
        for user in (self.student_a_user, self.organization):
            self.client.force_authenticate(user)
            response = self.client.post(URL, self.payload([self.student_a.pk]), format='json')
            self.assertEqual(response.status_code, 403)
        self.assertFalse(Task.objects.exists())

    def test_limits_and_shape(self):
        for students in ([], 'all', [str(self.student_a.pk)], [True], list(range(1, BULK_TASK_LIMIT + 2))):
            response = self.client.post(URL, self.payload(students), format='json')
            self.assertEqual(response.status_code, 400, students)
        self.assertFalse(Task.objects.exists())

    def test_query_count_does_not_grow_with_students(self):
        # SQLite caps bound parameters, so its INSERT is split in batches; PostgreSQL sends one.
        insert_fields = [field for field in Task._meta.concrete_fields if not isinstance(field, model_fields.AutoField)]

        def counts(n):
            Task.objects.all().delete()
            ids = [self.student_a.pk] + [self.add_student().pk for _ in range(n - 1)]
            with CaptureQueriesContext(connection) as queries:
                response = self.client.post(URL, self.payload(ids), format='json')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(Task.objects.count(), n)
            inserts = [query for query in queries if query['sql'].startswith('INSERT INTO "admissions_task"')]
            batch = connection.ops.bulk_batch_size(insert_fields, [None] * n)
            self.assertEqual(len(inserts), math.ceil(n / batch))
            return len(queries) - len(inserts)

        self.assertEqual(counts(5), counts(60))
