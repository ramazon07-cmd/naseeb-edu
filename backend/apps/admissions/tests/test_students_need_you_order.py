"""GET /api/students/?ordering=need_you: Home's "need you" rule, sorted in SQL."""
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.users.models import User

from ..models import Document, RoadmapMission, StudentProfile, Task
from .base import RoleIsolationBase


class NeedYouOrderingTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.past = timezone.localdate() - timedelta(days=3)
        self.client.force_authenticate(self.counselor)

    def add_student(self, first, last=''):
        user = User.objects.create_user(
            username=f'{first}-{last}-{User.objects.count()}'.lower(), email=f'{first}{User.objects.count()}@example.com',
            password='StrongPass123!', role=User.Role.STUDENT, school=self.school_a, first_name=first, last_name=last,
        )
        return StudentProfile.objects.create(user=user, school=self.school_a, assigned_counselor=self.counselor)

    def late_task(self, student, n=1):
        for index in range(n):
            Task.objects.create(student=student, title=f'Late {index}', due_date=self.past, status=Task.Status.TODO)

    def names(self, response):
        return [row['user_detail']['first_name'] for row in self.results(response)]

    def test_orders_by_reasons_then_late_items_then_name(self):
        self.student_a_user.first_name = 'Zed'
        self.student_a_user.save()
        calm = self.add_student('Amy')
        one_late = self.add_student('Bob')
        self.late_task(one_late)
        three_late = self.add_student('Cat')
        self.late_task(three_late, 3)
        two_reasons = self.add_student('Dan')
        self.late_task(two_reasons)
        Document.objects.create(student=two_reasons, title='Passport', status=Document.Status.REQUIRED)
        mission_late = self.add_student('Abe')
        RoadmapMission.objects.create(student=mission_late, title='M', status=RoadmapMission.Status.PLANNED, due_date=self.past)
        # Approved late-dated work is done: it is no reason.
        Task.objects.create(student=calm, title='Done', due_date=self.past, status=Task.Status.APPROVED)

        response = self.client.get('/api/students/', {'ordering': 'need_you'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ['Dan', 'Cat', 'Abe', 'Bob', 'Amy', 'Zed'])

    def test_cursor_pages_follow_the_same_order(self):
        for index in range(7):
            student = self.add_student(f'S{index}')
            self.late_task(student, index % 3)
        expected = self.names(self.client.get('/api/students/', {'ordering': 'need_you', 'page_size': 100}))
        seen, cursor = [], ''
        while True:
            response = self.client.get('/api/students/', {'ordering': 'need_you', 'cursor': cursor, 'page_size': 3})
            self.assertEqual(response.status_code, 200)
            seen += [row['user_detail']['first_name'] for row in response.data['results']]
            if not response.data['has_more']:
                break
            cursor = response.data['next'].split('cursor=')[1].split('&')[0]
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 8)

    def test_other_counselors_students_stay_out(self):
        self.late_task(self.student_b, 5)
        response = self.client.get('/api/students/', {'ordering': 'need_you'})
        self.assertNotIn(self.student_b.pk, [row['id'] for row in self.results(response)])

    def query_count(self, n):
        StudentProfile.objects.filter(assigned_counselor=self.counselor).exclude(pk=self.student_a.pk).delete()
        for index in range(n):
            student = self.add_student(f'Q{index}')
            self.late_task(student, index % 2)
            RoadmapMission.objects.create(student=student, title='M', status=RoadmapMission.Status.PLANNED, due_date=self.past)
            Document.objects.create(student=student, title='D', status=Document.Status.REQUIRED)
        for params in ({'ordering': 'need_you', 'page_size': 100}, {'ordering': 'need_you', 'cursor': '', 'page_size': 100}):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get('/api/students/', params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(self.results(response)), n + 1)
            yield len(queries)

    def test_query_count_is_constant(self):
        self.assertEqual(list(self.query_count(5)), list(self.query_count(60)))
