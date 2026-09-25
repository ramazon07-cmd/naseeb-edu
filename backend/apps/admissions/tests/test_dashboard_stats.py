"""Dashboard progress summary is computed in the database.

The expected values come from averaging the per-student ProgressStats that
the student list uses, so both screens always agree.
"""
import random
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions import progress, progress_cache
from apps.admissions.models import (
    Application, Document, RecommendationLetter, RoadmapMission, StudentProfile, Task, University,
)
from apps.admissions.scoping import student_scope_key, visible_students
from apps.admissions.tenancy import set_student_active
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.users.models import User

SUMMARY_KEYS = (
    'students_total', 'average_progress', 'average_task_progress', 'average_roadmap_progress',
    'average_journey_progress', 'students_at_risk',
)


def expected_summary(students):
    stats = progress.load_progress_stats(students)
    rows = [stats.get(pk) or progress.ProgressStats() for pk in students.order_by().values_list('pk', flat=True)]

    def average(attribute):
        values = [getattr(item, attribute) for item in rows]
        return progress.half_up(sum(values), len(values))

    return {
        'students_total': len(rows),
        'average_progress': average('progress_percent'),
        'average_task_progress': average('task_progress_percent'),
        'average_roadmap_progress': average('roadmap_progress_percent'),
        'average_journey_progress': average('journey_progress_percent'),
        'students_at_risk': sum(1 for item in rows if item.is_at_risk),
    }


class DashboardSummaryTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.university = University.objects.create(name='Summary U', country='USA')
        self.today = timezone.localdate()
        self._serial = 0

    def new_student(self, school=None, counselor=None):
        self._serial += 1
        school = school or self.school_a
        user = self.make_user(f'sum-{self._serial}', User.Role.STUDENT, school)
        return self.make_profile(user, school, counselor or self.counselor)

    def fill(self, profile, tasks=(), missions=(), applications=(), documents=(), letters=()):
        for index, (status_value, days) in enumerate(tasks):
            Task.objects.create(student=profile, title=f'T{index}', status=status_value,
                                due_date=self.today + timedelta(days=days))
        for index, (status_value, days) in enumerate(missions):
            RoadmapMission.objects.create(student=profile, title=f'M{index}', status=status_value,
                                          due_date=None if days is None else self.today + timedelta(days=days))
        for index, status_value in enumerate(applications):
            Application.objects.create(student=profile, university=self.university, program=f'P{index}',
                                       status=status_value)
        for index, status_value in enumerate(documents):
            Document.objects.create(student=profile, title=f'D{index}', status=status_value)
        for index, status_value in enumerate(letters):
            RecommendationLetter.objects.create(student=profile, recommender_name=f'R{index}', status=status_value)

    def seed_random(self, rng, count, **kwargs):
        for _ in range(count):
            self.fill(
                self.new_student(**kwargs),
                tasks=[(rng.choice(Task.Status.values), rng.randint(-5, 5)) for _ in range(rng.randint(0, 9))],
                missions=[(rng.choice(RoadmapMission.Status.values), rng.choice([None, -3, 0, 4]))
                          for _ in range(rng.randint(0, 6))],
                applications=[rng.choice(Application.Status.values) for _ in range(rng.randint(0, 5))],
                documents=[rng.choice(Document.Status.values) for _ in range(rng.randint(0, 5))],
                letters=[rng.choice(RecommendationLetter.Status.values) for _ in range(rng.randint(0, 3))],
            )

    def seed_edges(self):
        # 1 of 8 done -> 12.5 exactly, rounded half up to 13.
        self.fill(self.new_student(), tasks=[('approved', 3)] + [('todo', 3)] * 7)
        # 23 of 40 done -> exactly 57.5 (the float would say 57.49…): 58.
        self.fill(self.new_student(), tasks=[('approved', 1)] * 23 + [('todo', 1)] * 17)
        # Journey (5 + 50) / 2 = 27.5 -> 28.
        self.fill(self.new_student(), tasks=[('todo', 1)] * 7 + [('in_progress', 1)],
                  missions=[('completed', None), ('planned', None)])
        # Late status counts as risk even with a future due date.
        self.fill(self.new_student(), tasks=[('late', 10)])
        # Nothing at all.
        self.new_student()

    def summary(self, user):
        self.client.force_authenticate(user)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, 200, response.data)
        return {key: response.data[key] for key in SUMMARY_KEYS}

    def scope(self, user):
        return visible_students(user).filter(user__is_active=True, deactivated_at__isnull=True)

    def test_matches_per_student_stats_on_mixed_data(self):
        rng = random.Random(20260925)
        self.seed_edges()
        self.seed_random(rng, 60)
        self.seed_random(rng, 15, school=self.school_b, counselor=self.counselor_b)
        for user in (self.admin, self.counselor, self.teacher, self.organization, self.counselor_b, self.student_user):
            with self.subTest(user=user.username):
                expected = expected_summary(self.scope(user))
                self.assertEqual(progress.summarize_progress(self.scope(user)), expected)
                self.assertEqual(self.summary(user), expected)
        self.assertEqual(self.summary(self.counselor)['students_total'], 66)

    def test_rounding_edge_cases(self):
        self.seed_edges()
        students = StudentProfile.objects.filter(pk__in=self.scope(self.counselor).exclude(pk=self.student.pk))
        self.assertEqual(progress.summarize_progress(students), expected_summary(students))
        values = {item.progress_percent for item in progress.load_progress_stats(students).values()}
        self.assertLessEqual({13, 58}, values)

    def test_deactivated_students_are_left_out(self):
        self.fill(self.new_student(), tasks=[('late', -1)], applications=['submitted'], documents=['uploaded'])
        leaving = self.new_student()
        self.fill(leaving, tasks=[('late', -1), ('todo', -2)], applications=['submitted'], documents=['uploaded'])
        self.client.force_authenticate(self.admin)
        before = self.client.get('/api/dashboard/stats/').data
        set_student_active(leaving, False, self.admin)
        for user in (self.admin, self.counselor):
            with self.subTest(user=user.username):
                self.assertEqual(self.summary(user), expected_summary(self.scope(user)))
        self.client.force_authenticate(self.admin)
        after = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(after['students_total'], before['students_total'] - 1)
        self.assertEqual(after['students_at_risk'], before['students_at_risk'] - 1)
        self.assertEqual(after['tasks_total'], before['tasks_total'] - 2)
        self.assertEqual(after['applications_submitted'], before['applications_submitted'] - 1)
        self.assertEqual(after['documents_pending_review'], before['documents_pending_review'] - 1)

    def test_scales_without_loading_students(self):
        pattern = dict(
            tasks=[('approved', -1), ('in_progress', -1), ('todo', 2)],
            missions=[('completed', None), ('planned', -1)],
            applications=['submitted', 'applying'],
            documents=['approved'],
        )

        def add(count):
            for _ in range(count):
                self.fill(self.new_student(), **pattern)

        loaded = []
        real_from_db = StudentProfile.from_db.__func__

        def tracking_from_db(cls, *args, **kwargs):
            loaded.append(cls)
            return real_from_db(cls, *args, **kwargs)

        def run():
            loaded.clear()
            cache.clear()
            with mock.patch.object(StudentProfile, 'from_db', classmethod(tracking_from_db)), \
                    mock.patch.object(progress, 'load_progress_stats', side_effect=AssertionError('per-student load')):
                queries, response = self.get_counted('/api/dashboard/stats/')
            self.assertEqual(loaded, [])
            return queries, response.data

        self.client.force_authenticate(self.counselor)
        StudentProfile.objects.filter(pk=self.student.pk).delete()
        add(4)
        few_queries, few = run()
        add(8)
        many_queries, many = run()
        self.assertEqual(few_queries, many_queries)
        for key in SUMMARY_KEYS[1:5]:
            self.assertEqual(few[key], many[key], key)
        self.assertEqual((few['students_total'], many['students_total']), (4, 12))
        self.assertEqual((few['students_at_risk'], many['students_at_risk']), (4, 12))
        self.assertEqual((few['tasks_total'], many['tasks_total']), (12, 36))

    def test_summary_is_one_grouped_query_whatever_the_roster(self):
        pattern = dict(tasks=[('approved', -1), ('late', 2)], missions=[('completed', None)],
                       applications=['submitted'], documents=['approved'])

        def measure(count):
            for _ in range(count):
                self.fill(self.new_student(), **pattern)
            with CaptureQueriesContext(connection) as context:
                summary = progress.summarize_progress(self.scope(self.counselor))
            return summary, [query['sql'] for query in context.captured_queries]

        few, few_sql = measure(3)
        many, many_sql = measure(6)
        self.assertEqual((len(few_sql), len(many_sql)), (1, 1))
        self.assertEqual((few['students_total'], many['students_total']), (4, 10))
        # Each related table is grouped once; nothing is evaluated per student row.
        self.assertEqual(many_sql[0].count('GROUP BY'), 5)
        self.assertNotRegex(many_sql[0], r'= \("admissions_studentprofile"\."id"\)')

    def test_empty_scope_needs_no_query(self):
        with CaptureQueriesContext(connection) as context:
            summary = progress.summarize_progress(StudentProfile.objects.none())
        self.assertEqual(len(context.captured_queries), 0)
        self.assertEqual(summary, dict.fromkeys(SUMMARY_KEYS, 0))

    def test_summary_is_cached_per_student_scope(self):
        self.fill(self.new_student(), tasks=[('late', -1)])
        self.fill(self.new_student(school=self.school_b, counselor=self.counselor_b), tasks=[('approved', 1)])
        first = self.summary(self.counselor)
        # Between writes the summary comes from the cache: no summary query.
        with mock.patch.object(progress_cache, 'summarize_progress', side_effect=AssertionError('recomputed')):
            self.assertEqual(self.summary(self.counselor), first)
        other = self.summary(self.counselor_b)
        self.assertEqual(other, expected_summary(self.scope(self.counselor_b)))
        self.assertNotEqual(other, first)

    def test_every_write_feeding_the_summary_refreshes_it(self):
        student = self.new_student()
        task = Task.objects.create(student=student, title='T', due_date=self.today + timedelta(days=1))
        self.assertEqual(self.summary(self.counselor)['students_total'], 2)
        self.new_student()
        self.assertEqual(self.summary(self.counselor)['students_total'], 3)
        task.status = Task.Status.APPROVED
        task.save()
        self.assertEqual(self.summary(self.counselor), expected_summary(self.scope(self.counselor)))
        set_student_active(student, False, self.admin)
        self.assertEqual(self.summary(self.counselor)['students_total'], 2)
        # A counselor who leaves the school loses the assignment (a bulk update).
        from apps.admissions.tenancy import user_left_school

        self.counselor.school = self.school_b
        self.counselor.save(update_fields=['school'])
        user_left_school(self.counselor, self.school_a)
        self.assertEqual(self.summary(self.counselor)['students_total'], 0)

    def test_sign_in_does_not_drop_the_cache(self):
        self.summary(self.counselor)
        version = cache.get(progress_cache.VERSION_KEY)
        self.counselor.last_login = timezone.now()
        self.counselor.save(update_fields=['last_login'])
        self.assertEqual(cache.get(progress_cache.VERSION_KEY), version)

    def test_scope_keys_separate_tenants(self):
        keys = {user.username: student_scope_key(user) for user in (
            self.admin, self.counselor, self.counselor_peer, self.counselor_b, self.teacher, self.organization,
            self.student_user, self.parent,
        )}
        self.assertEqual(keys['base-admin'], 'all')
        self.assertIsNone(keys['base-parent'])
        self.assertEqual(keys['base-teacher'], keys['base-org'])
        scoped = [key for name, key in keys.items() if name not in {'base-admin', 'base-parent', 'base-org'}]
        self.assertEqual(len(set(scoped)), len(scoped))
