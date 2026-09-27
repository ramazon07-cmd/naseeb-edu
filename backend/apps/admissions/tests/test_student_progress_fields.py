"""The per-student numbers the student dashboard and roadmap page show (docs/metrics.md)."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ..models import Achievement, Application, Honor, RoadmapMission, University
from ..progress import load_progress_stats
from .base import RoleIsolationBase


class StudentProgressFieldsTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.student_a.level = 2
        self.student_a.save(update_fields=['level'])
        # Level 1: 3 of 3 approved; level 2: 1 of 4 approved.
        for sequence in range(1, 4):
            RoadmapMission.objects.create(student=self.student_a, title=f'L1-{sequence}', level=1,
                                          sequence=sequence, status=RoadmapMission.Status.COMPLETED)
        for sequence, status in enumerate(['completed', 'submitted', 'in_progress', 'planned'], start=1):
            RoadmapMission.objects.create(student=self.student_a, title=f'L2-{sequence}', level=2,
                                          sequence=sequence, status=status)
        university = University.objects.create(name='Fields U', country='USA')
        for index, status in enumerate(['researching', 'submitted', 'accepted', 'accepted', 'rejected']):
            Application.objects.create(student=self.student_a, university=university, program=f'P{index}', status=status)
        Achievement.objects.create(student=self.student_a, title='Olympiad')
        Honor.objects.create(student=self.student_a, title='Dean list')
        Honor.objects.create(student=self.student_a, title='Merit')
        # Another student's records never leak into these counts.
        Achievement.objects.create(student=self.student_b, title='Other')

    def own_profile(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, 200)
        return self.results(response)[0]

    def test_roadmap_overall_and_level_numbers_are_distinct_backend_fields(self):
        data = self.own_profile()
        self.assertEqual(data['roadmap_stars'], 4)
        self.assertEqual(sum(data['roadmap_status_counts'].values()), 7)
        # Roadmap progress counts every mission, not only the current level.
        self.assertEqual(data['roadmap_progress_percent'], 57)
        self.assertEqual((data['level_missions_approved'], data['level_missions_total']), (1, 4))

    def test_application_and_achievement_counts(self):
        data = self.own_profile()
        self.assertEqual(data['applications_total'], 5)
        self.assertEqual(data['applications_submitted'], 4)
        self.assertEqual(data['applications_accepted'], 2)
        self.assertEqual(data['achievements_total'], 3)

    def test_student_without_records_gets_zeros(self):
        self.client.force_authenticate(self.student_b_user)
        data = self.results(self.client.get('/api/students/'))[0]
        self.assertEqual(data['achievements_total'], 1)
        for key in ('level_missions_approved', 'level_missions_total', 'applications_total',
                    'applications_submitted', 'applications_accepted'):
            self.assertEqual(data[key], 0, key)

    def test_batch_load_is_a_constant_number_of_queries(self):
        with CaptureQueriesContext(connection) as context:
            stats = load_progress_stats([self.student_a.pk, self.student_b.pk])
        self.assertEqual(len(context.captured_queries), 6)
        self.assertEqual(stats[self.student_a.pk].achievements_total, 3)
        self.assertEqual(stats[self.student_a.pk].level_missions(1), (3, 3))
        self.assertEqual(stats[self.student_a.pk].mission_counts['completed'], 4)
