"""GET /api/review/today/: the counselor's own approvals and send-backs since
midnight in Tashkent, newest first, for their own students only."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Achievement, ActivityLog, Document, RoadmapMission, Task
from apps.admissions.views.review_today import today_start

from ..test_audit_base import AuditBaseMixin

URL = '/api/review/today/'


class ReviewedTodayTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)

    def entries(self, expected_status=200):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, expected_status, getattr(response, 'data', None))
        return response.data.get('results') if expected_status == 200 else response.data

    def log(self, action, *, actor=None, student=None, at=None, **metadata):
        entry = ActivityLog.objects.create(
            actor=actor or self.counselor, student=student or self.student, action=action, metadata=metadata,
        )
        if at is not None:
            ActivityLog.objects.filter(pk=entry.pk).update(created_at=at)
        return entry

    def test_every_kind_of_decision_through_the_real_actions_newest_first(self):
        due = timezone.localdate() + timedelta(days=3)
        task = Task.objects.create(student=self.student, title='Essay outline', status=Task.Status.SUBMITTED, due_date=due)
        document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x')
        mission = RoadmapMission.objects.create(student=self.student, title='Visit campus', status=RoadmapMission.Status.SUBMITTED)
        achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        sent_back = Task.objects.create(student=self.student, title='Draft CV', status=Task.Status.SUBMITTED, due_date=due)

        for path in (
            f'/api/tasks/{task.pk}/approve/',
            f'/api/documents/{document.pk}/approve/',
            f'/api/roadmap-missions/{mission.pk}/approve/',
            f'/api/achievements/{achievement.pk}/approve/',
        ):
            self.assertEqual(self.client.post(path, {'note': ''}, format='json').status_code, 200, path)
        response = self.client.post(f'/api/tasks/{sent_back.pk}/send-back/', {'note': 'Add dates.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        rows = [(row['kind'], row['decision'], row['record_id'], row['title']) for row in self.entries()]
        self.assertEqual(rows, [
            ('task', 'sent_back', sent_back.pk, 'Draft CV'),
            ('portfolio', 'approved', achievement.pk, 'Olympiad'),
            ('roadmap', 'approved', mission.pk, 'Visit campus'),
            ('document', 'approved', document.pk, 'Transcript'),
            ('task', 'approved', task.pk, 'Essay outline'),
        ])
        first = self.entries()[0]
        self.assertEqual((first['student_id'], first['student_name']), (self.student.pk, 'base-student'))

    def test_only_since_midnight_in_tashkent(self):
        midnight = today_start()
        self.assertEqual(timezone.localtime(midnight).utcoffset(), timedelta(hours=5))
        self.log('Document approved: Late last night', record=1, at=midnight - timedelta(minutes=1))
        self.log('Document approved: Just after midnight', record=2, at=midnight + timedelta(minutes=1))
        self.assertEqual([row['title'] for row in self.entries()], ['Just after midnight'])

    def test_other_timeline_entries_are_left_out(self):
        self.log('Reminder sent: Transcript', record=3)
        self.log('Task created: Transcript')
        self.log('Task approved: Transcript (+20 XP)', task=4)
        self.log('Self-task approved: Plan (no XP)', task=5)
        self.assertEqual([(row['title'], row['record_id']) for row in self.entries()], [('Plan', 5), ('Transcript', 4)])

    def test_another_counselors_decisions_are_not_mine(self):
        self.log('Document approved: Peer work', actor=self.counselor_peer, record=6)
        self.assertEqual(self.entries(), [])

    def test_cross_school_rows_never_show(self):
        # counselor_b's own decisions on their own school's student...
        self.log('Document approved: School B transcript', actor=self.counselor_b, student=self.student_b, record=7)
        self.assertEqual(self.entries(), [])
        # ...and a row naming this counselor on a student in another school.
        self.log('Document approved: Stray row', student=self.student_b, record=8)
        self.assertEqual(self.entries(), [])

        self.client.force_authenticate(self.counselor_b)
        self.assertEqual([row['title'] for row in self.entries()], ['School B transcript'])

    def test_a_student_moved_to_another_counselor_drops_out(self):
        self.log('Document approved: Transcript', record=9)
        self.student.assigned_counselor = self.counselor_peer
        self.student.save(update_fields=['assigned_counselor'])
        self.assertEqual(self.entries(), [])

    def test_students_and_parents_are_refused(self):
        for user in (self.student_user, self.parent):
            self.client.force_authenticate(user)
            self.entries(expected_status=403)

    def test_teachers_see_their_own_decisions(self):
        self.log('Task approved: Lab report (+10 XP)', actor=self.teacher, task=10)
        self.client.force_authenticate(self.teacher)
        self.assertEqual([row['title'] for row in self.entries()], ['Lab report'])

    def test_query_count_does_not_grow_with_rows(self):
        self.log('Document approved: One', record=11)
        few, _ = self.get_counted(URL)
        for index in range(12):
            self.log(f'Achievement sent back: Item {index}', record=100 + index)
        many, response = self.get_counted(URL)
        self.assertEqual(len(response.data['results']), 13)
        self.assertEqual(few, many)
