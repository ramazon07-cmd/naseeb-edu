"""The counselor workspace ("Counselor Dashboard" design): review counts, send-back and
approve-with-note, the reminder, per-student missing/next-deadline fields.

Every permission test proves the negative case: another counselor, a student,
a teacher or an organization account must not be able to do it or see it.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from apps.admissions.models import (
    Achievement, ActivityLog, Application, Booking, Document, Essay, Notification, RecommendationLetter,
    RoadmapMission, Task, University, XPTransaction,
)
from apps.admissions.progress import load_progress_stats
from apps.users.models import User

from ..test_audit_base import AuditBaseMixin


class WorkspaceBase(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()

    def act_as(self, user):
        self.client.force_authenticate(user)

    def task(self, student=None, **fields):
        fields.setdefault('title', 'Personal Statement draft')
        fields.setdefault('due_date', self.today + timedelta(days=3))
        return Task.objects.create(student=student or self.student, **fields)


class DashboardCounselorSummaryTests(WorkspaceBase):
    URL = '/api/dashboard/stats/'

    def test_counts_what_is_waiting_and_who_needs_the_counselor(self):
        self.task(status=Task.Status.SUBMITTED)
        self.task(status=Task.Status.TODO, due_date=self.today - timedelta(days=2))  # late
        Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED)
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        RoadmapMission.objects.create(student=self.student, title='Shortlist', status=RoadmapMission.Status.SUBMITTED)
        Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')
        Achievement.objects.create(
            student=self.student, title='Sent back', category='olympiad', description='x', counselor_comment='More proof',
        )
        Achievement.objects.create(student=self.student, title='Verified', category='other', description='y', verified=True)
        Essay.objects.create(student=self.student, title='PS', status=Essay.Status.REVIEWING, shared_with_counselor=True)
        Essay.objects.create(student=self.student, title='Private', status=Essay.Status.REVIEWING, shared_with_counselor=False)
        self.act_as(self.counselor)
        data = self.client.get(self.URL).data
        self.assertEqual(data['review'], {'tasks': 1, 'documents': 1, 'roadmap': 1, 'portfolio': 1, 'essays': 1})
        # Late work and a missing document are the same student: one student needs them.
        self.assertEqual(data['students_need_you'], 1)

    def test_other_counselors_work_is_not_counted(self):
        self.task(student=self.student_b, status=Task.Status.SUBMITTED, due_date=self.today - timedelta(days=5))
        Document.objects.create(student=self.student_b, title='Passport', status=Document.Status.REQUIRED)
        self.act_as(self.counselor)
        data = self.client.get(self.URL).data
        self.assertEqual(data['review']['tasks'], 0)
        self.assertEqual(data['students_need_you'], 0)
        self.assertEqual(data['deadlines'], [])

    def test_deadlines_span_tasks_applications_and_letters_soonest_first(self):
        self.task(title='IELTS certificate', due_date=self.today + timedelta(days=2))
        self.task(title='Far away', due_date=self.today + timedelta(days=30))
        self.task(title='Approved already', status=Task.Status.APPROVED, due_date=self.today - timedelta(days=1))
        university = University.objects.create(name='NUS', country='Singapore')
        Application.objects.create(
            student=self.student, university=university, program='CS', deadline=self.today + timedelta(days=4),
        )
        RecommendationLetter.objects.create(
            student=self.student, recommender_name='Mr Karimov', deadline=self.today - timedelta(days=3),
            status=RecommendationLetter.Status.REQUESTED,
        )
        self.act_as(self.counselor)
        deadlines = self.client.get(self.URL).data['deadlines']
        self.assertEqual([row['kind'] for row in deadlines], ['letter', 'task', 'application'])
        self.assertEqual([row['late'] for row in deadlines], [True, False, False])
        self.assertEqual(deadlines[0]['title'], 'Mr Karimov')
        self.assertEqual(deadlines[2]['title'], 'NUS')

    def test_only_counselors_get_the_workspace_fields(self):
        self.task(status=Task.Status.SUBMITTED)
        for user in (self.teacher, self.organization):
            self.act_as(user)
            data = self.client.get(self.URL).data
            for key in ('review', 'students_need_you', 'deadlines'):
                self.assertNotIn(key, data, f'{user.username} must not receive {key}')


class SendBackTests(WorkspaceBase):
    def setUp(self):
        super().setUp()
        self.submitted_task = self.task(status=Task.Status.SUBMITTED)
        self.mission = RoadmapMission.objects.create(student=self.student, title='Shortlist 8', status=RoadmapMission.Status.SUBMITTED)
        self.document = Document.objects.create(student=self.student, title='IELTS (PDF)', status=Document.Status.UPLOADED)
        self.achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')

    def send_back(self, resource, record, note='Add one concrete example.'):
        return self.client.post(f'/api/{resource}/{record.pk}/send-back/', {'note': note}, format='json')

    def test_task_returns_to_in_progress_and_tells_the_student(self):
        self.act_as(self.counselor)
        response = self.send_back('tasks', self.submitted_task)
        self.assertEqual(response.status_code, 200, response.data)
        self.submitted_task.refresh_from_db()
        self.assertEqual(self.submitted_task.status, Task.Status.IN_PROGRESS)
        notice = Notification.objects.get(student=self.student, kind=Notification.Kind.TASK)
        self.assertEqual(notice.title, 'Your counselor asked for changes')
        self.assertEqual(notice.message, 'Personal Statement draft: Add one concrete example.')
        self.assertEqual(notice.target_id, self.submitted_task.pk)
        self.assertTrue(ActivityLog.objects.filter(student=self.student, action='Task sent back: Personal Statement draft').exists())

    def test_mission_document_and_achievement_are_returned_with_the_note_kept(self):
        self.act_as(self.counselor)
        self.assertEqual(self.send_back('roadmap-missions', self.mission).status_code, 200)
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.status, RoadmapMission.Status.IN_PROGRESS)

        self.assertEqual(self.send_back('documents', self.document, 'Scan the full page.').status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual((self.document.status, self.document.counselor_comment), (Document.Status.REJECTED, 'Scan the full page.'))

        self.assertEqual(self.send_back('achievements', self.achievement, 'Attach the diploma.').status_code, 200)
        self.achievement.refresh_from_db()
        self.assertEqual((self.achievement.verified, self.achievement.counselor_comment), (False, 'Attach the diploma.'))

    def test_a_note_is_required_and_bounded(self):
        self.act_as(self.counselor)
        self.assertEqual(self.send_back('tasks', self.submitted_task, note='   ').status_code, 400)
        self.assertEqual(self.send_back('tasks', self.submitted_task, note='x' * 2001).status_code, 400)
        self.submitted_task.refresh_from_db()
        self.assertEqual(self.submitted_task.status, Task.Status.SUBMITTED)

    def test_only_work_waiting_for_review_can_be_sent_back(self):
        self.act_as(self.counselor)
        todo = self.task(status=Task.Status.TODO)
        self.assertEqual(self.send_back('tasks', todo).status_code, 400)
        approved = Document.objects.create(student=self.student, title='Approved doc', status=Document.Status.APPROVED)
        self.assertEqual(self.send_back('documents', approved).status_code, 400)
        self.achievement.verified = True
        self.achievement.save()
        self.assertEqual(self.send_back('achievements', self.achievement).status_code, 400)
        self.assertFalse(Notification.objects.exists())

    def test_wrong_people_cannot_send_work_back(self):
        # A student (even the owner), another school's counselor and an organization account.
        for user in (self.student_user, self.counselor_b, self.organization):
            self.act_as(user)
            for resource, record in (('tasks', self.submitted_task), ('roadmap-missions', self.mission), ('documents', self.document), ('achievements', self.achievement)):
                response = self.send_back(resource, record)
                self.assertIn(response.status_code, (403, 404), f'{user.username} on {resource}: {response.status_code}')
        self.submitted_task.refresh_from_db()
        self.assertEqual(self.submitted_task.status, Task.Status.SUBMITTED)
        self.assertFalse(Notification.objects.exists())

    def test_a_teacher_may_return_tasks_and_missions_but_not_documents_or_portfolio(self):
        self.act_as(self.teacher)
        self.assertEqual(self.send_back('tasks', self.submitted_task).status_code, 200)
        self.assertEqual(self.send_back('roadmap-missions', self.mission).status_code, 200)
        self.assertEqual(self.send_back('documents', self.document).status_code, 403)
        self.assertEqual(self.send_back('achievements', self.achievement).status_code, 403)


class ApproveWithNoteTests(WorkspaceBase):
    def setUp(self):
        super().setUp()
        self.document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED, counselor_comment='old')
        self.achievement = Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='Silver')

    def test_document_and_achievement_are_approved_and_the_note_replaces_the_old_comment(self):
        self.act_as(self.counselor)
        response = self.client.post(f'/api/documents/{self.document.pk}/approve/', {'note': 'Perfect scan.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.document.refresh_from_db()
        self.assertEqual((self.document.status, self.document.counselor_comment), (Document.Status.APPROVED, 'Perfect scan.'))
        self.assertEqual(Notification.objects.get(kind=Notification.Kind.DOCUMENT).message, 'Transcript: Perfect scan.')

        response = self.client.post(f'/api/achievements/{self.achievement.pk}/approve/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.achievement.refresh_from_db()
        self.assertTrue(self.achievement.verified)
        # No note, no notice.
        self.assertEqual(Notification.objects.count(), 1)
        self.assertTrue(ActivityLog.objects.filter(action='Achievement approved: Olympiad').exists())

    def test_a_task_approval_note_reaches_the_student_only_when_given(self):
        submitted = self.task(status=Task.Status.SUBMITTED, priority=Task.Priority.URGENT)
        quiet = self.task(title='No note', status=Task.Status.SUBMITTED)
        self.act_as(self.counselor)
        response = self.client.post(f'/api/tasks/{submitted.pk}/approve/', {'note': 'Well done.'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['xp_awarded'], 100)
        self.assertEqual(self.client.post(f'/api/tasks/{quiet.pk}/approve/', {}, format='json').status_code, 200)
        notices = Notification.objects.filter(kind=Notification.Kind.TASK)
        self.assertEqual([notice.message for notice in notices], ['Personal Statement draft: Well done.'])

    def test_students_and_other_schools_cannot_approve(self):
        for user in (self.student_user, self.counselor_b, self.organization):
            self.act_as(user)
            for resource, record in (('documents', self.document), ('achievements', self.achievement)):
                response = self.client.post(f'/api/{resource}/{record.pk}/approve/', {}, format='json')
                self.assertIn(response.status_code, (403, 404), f'{user.username} on {resource}')
        self.achievement.refresh_from_db()
        self.assertFalse(self.achievement.verified)

    def test_the_xp_a_task_will_award_is_in_the_payload(self):
        self.act_as(self.counselor)
        urgent = self.task(priority=Task.Priority.URGENT, status=Task.Status.SUBMITTED)
        own = self.task(is_self_assigned=True, priority=Task.Priority.URGENT)
        self.assertEqual(self.client.get(f'/api/tasks/{urgent.pk}/').data['xp_reward'], 100)
        self.assertEqual(self.client.get(f'/api/tasks/{own.pk}/').data['xp_reward'], 0)


class PortfolioReviewTests(WorkspaceBase):
    def setUp(self):
        super().setUp()
        self.waiting = Achievement.objects.create(student=self.student, title='Waiting', category='other', description='a')
        self.returned = Achievement.objects.create(student=self.student, title='Returned', category='other', description='b', counselor_comment='Fix it')
        self.verified = Achievement.objects.create(student=self.student, title='Verified', category='other', description='c', verified=True)

    def test_awaiting_review_filter_excludes_verified_and_returned_records(self):
        self.act_as(self.counselor)
        rows = self.results(self.client.get('/api/achievements/?awaiting_review=true&cursor='))
        self.assertEqual([row['title'] for row in rows], ['Waiting'])
        rows = self.results(self.client.get('/api/achievements/?awaiting_review=false&cursor='))
        self.assertEqual({row['title'] for row in rows}, {'Returned', 'Verified'})
        self.assertEqual(self.client.get('/api/achievements/?awaiting_review=maybe').status_code, 400)

    def test_documents_awaiting_review_are_uploaded_or_reviewing(self):
        for status in ('required', 'uploaded', 'reviewing', 'approved', 'rejected'):
            Document.objects.create(student=self.student, title=f'doc-{status}', status=status)
        self.act_as(self.counselor)
        rows = self.results(self.client.get('/api/documents/?awaiting_review=true&cursor='))
        self.assertEqual({row['title'] for row in rows}, {'doc-uploaded', 'doc-reviewing'})

    def test_a_student_cannot_write_the_review_comment_or_verify_their_own_work(self):
        self.act_as(self.student_user)
        response = self.client.patch(f'/api/achievements/{self.waiting.pk}/', {'counselor_comment': 'Approved!'}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/achievements/{self.waiting.pk}/', {'verified': True}, format='json')
        self.assertEqual(response.status_code, 400)
        self.waiting.refresh_from_db()
        self.assertEqual((self.waiting.verified, self.waiting.counselor_comment), (False, ''))

    def test_editing_a_returned_record_puts_it_back_in_the_queue(self):
        self.act_as(self.student_user)
        response = self.client.patch(f'/api/achievements/{self.returned.pk}/', {'description': 'now with proof'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.returned.refresh_from_db()
        self.assertEqual(self.returned.counselor_comment, '')
        self.act_as(self.counselor)
        rows = self.results(self.client.get('/api/achievements/?awaiting_review=true&cursor='))
        self.assertEqual({row['title'] for row in rows}, {'Waiting', 'Returned'})


class ReminderTests(WorkspaceBase):
    def url(self, student=None):
        return f'/api/students/{(student or self.student).pk}/remind/'

    def test_a_late_task_reminder_reaches_the_student_once(self):
        task = self.task(status=Task.Status.TODO, due_date=self.today - timedelta(days=1))
        self.act_as(self.counselor)
        response = self.client.post(self.url(), {'topic': 'task', 'record': task.pk}, format='json')
        self.assertEqual((response.status_code, response.data), (201, {'sent': True}))
        notice = Notification.objects.get(student=self.student)
        self.assertEqual((notice.title, notice.kind, notice.target_id), ('Your counselor sent a reminder', Notification.Kind.TASK, task.pk))
        self.assertIn(task.due_date.isoformat(), notice.message)
        # A second click inside the cooldown adds nothing.
        response = self.client.post(self.url(), {'topic': 'task', 'record': task.pk}, format='json')
        self.assertEqual((response.status_code, response.data), (200, {'sent': False}))
        self.assertEqual(Notification.objects.count(), 1)

    def test_document_mission_and_profile_reminders(self):
        document = Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        mission = RoadmapMission.objects.create(student=self.student, title='Research 10', status=RoadmapMission.Status.IN_PROGRESS)
        self.act_as(self.counselor)
        for payload in ({'topic': 'document', 'record': document.pk}, {'topic': 'mission', 'record': mission.pk}, {'topic': 'profile'}):
            self.assertEqual(self.client.post(self.url(), payload, format='json').status_code, 201, payload)
        self.assertEqual(Notification.objects.count(), 3)
        self.assertTrue(ActivityLog.objects.filter(action='Reminder sent: Passport').exists())

    def test_bad_input_is_a_400_and_sends_nothing(self):
        approved = self.task(status=Task.Status.APPROVED)
        other = self.task(student=self.student_b)
        self.act_as(self.counselor)
        for payload in ({}, {'topic': 'nope'}, {'topic': 'task'}, {'topic': 'task', 'record': approved.pk}, {'topic': 'task', 'record': other.pk}):
            self.assertEqual(self.client.post(self.url(), payload, format='json').status_code, 400, payload)
        self.assertFalse(Notification.objects.exists())

    def test_only_the_assigned_counselor_can_remind(self):
        for user, expected in ((self.counselor_b, 404), (self.counselor_peer, 404), (self.student_user, 403), (self.teacher, 403), (self.organization, 403)):
            self.act_as(user)
            response = self.client.post(self.url(), {'topic': 'profile'}, format='json')
            self.assertEqual(response.status_code, expected, f'{user.username}: {response.status_code}')
        self.assertFalse(Notification.objects.exists())


class StudentProgressFieldTests(WorkspaceBase):
    def stats(self):
        return load_progress_stats([self.student.pk])[self.student.pk]

    def test_a_missing_document_is_named_and_counted(self):
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        Document.objects.create(student=self.student, title='Transcript', status=Document.Status.REQUIRED)
        Document.objects.create(student=self.student, title='CV', status=Document.Status.UPLOADED)
        stats = self.stats()
        self.assertEqual((stats.documents_missing, stats.missing_document_title), (2, 'Passport'))
        self.act_as(self.counselor)
        row = self.client.get(f'/api/students/{self.student.pk}/').data
        self.assertEqual((row['documents_missing'], row['missing_document_title']), (2, 'Passport'))

    def test_unverified_portfolio_counts_as_waiting_for_review(self):
        Achievement.objects.create(student=self.student, title='A', category='other', description='a')
        Achievement.objects.create(student=self.student, title='B', category='other', description='b', verified=True)
        Achievement.objects.create(student=self.student, title='C', category='other', description='c', counselor_comment='Fix')
        self.assertEqual(self.stats().to_review_total, 1)

    def test_next_deadline_is_the_earliest_open_one_across_sources(self):
        self.task(title='Later task', due_date=self.today + timedelta(days=10))
        self.task(title='Sooner task', due_date=self.today + timedelta(days=5))
        self.task(title='Done', status=Task.Status.APPROVED, due_date=self.today - timedelta(days=9))
        self.assertEqual(self.stats().next_deadline(self.today), {
            'kind': 'task', 'title': 'Sooner task', 'due': (self.today + timedelta(days=5)).isoformat(), 'late': False,
        })
        university = University.objects.create(name='NUS', country='Singapore')
        Application.objects.create(student=self.student, university=university, program='CS', deadline=self.today + timedelta(days=2))
        self.assertEqual(self.stats().next_deadline(self.today)['kind'], 'application')
        RecommendationLetter.objects.create(student=self.student, recommender_name='Mr K', deadline=self.today - timedelta(days=1))
        found = self.stats().next_deadline(self.today)
        self.assertEqual((found['kind'], found['title'], found['late']), ('letter', 'Mr K', True))

    def test_no_open_work_means_no_deadline(self):
        self.task(status=Task.Status.SUBMITTED)
        self.assertIsNone(self.stats().next_deadline(self.today))

    def test_the_new_fields_cost_no_extra_queries(self):
        with CaptureQueriesContext(connection) as context:
            load_progress_stats([self.student.pk, self.student_b.pk])
        self.assertEqual(len(context.captured_queries), 6)


class BookingPreviousTimeTests(WorkspaceBase):
    def test_rescheduling_remembers_where_the_meeting_was(self):
        original = timezone.now() + timedelta(days=3)
        booking = Booking.objects.create(
            student=self.student, participant=self.counselor, topic='SAT plan', starts_at=original,
            status=Booking.Status.APPROVED,
        )
        self.act_as(self.counselor)
        moved = original + timedelta(days=1)
        response = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {'starts_at': moved.isoformat()}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.previous_starts_at, original)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(parse_datetime(response.data['previous_starts_at']), original)

    def test_a_student_cannot_set_the_previous_time_directly(self):
        booking = Booking.objects.create(
            student=self.student, participant=self.counselor, topic='SAT plan',
            starts_at=timezone.now() + timedelta(days=3), status=Booking.Status.PENDING,
        )
        self.act_as(self.student_user)
        self.client.patch(f'/api/bookings/{booking.pk}/', {'previous_starts_at': timezone.now().isoformat()}, format='json')
        booking.refresh_from_db()
        self.assertIsNone(booking.previous_starts_at)


class ActivityFeedFilterTests(WorkspaceBase):
    def test_a_counselor_reads_one_students_recent_activity_and_no_one_elses(self):
        mine = ActivityLog.objects.create(actor=self.counselor, student=self.student, action='Task approved: X (+50 XP)')
        ActivityLog.objects.create(actor=self.counselor_b, student=self.student_b, action='Other school')
        self.act_as(self.counselor)
        rows = self.results(self.client.get(f'/api/activity/?student={self.student.pk}&cursor=&page_size=5'))
        self.assertEqual([row['id'] for row in rows], [mine.pk])
        # The filter narrows the caller's scope; it never widens it.
        rows = self.results(self.client.get(f'/api/activity/?student={self.student_b.pk}&cursor=&page_size=5'))
        self.assertEqual(rows, [])


class SameSchoolCounselorIsolationTests(WorkspaceBase):
    """Two counselors of one school: neither sees, counts or acts on the other's students."""

    def setUp(self):
        super().setUp()
        peer_user = self.make_user('peer-student', User.Role.STUDENT, self.school_a)
        self.peer_student = self.make_profile(peer_user, self.school_a, self.counselor_peer)
        self.peer_task = self.task(student=self.peer_student, status=Task.Status.SUBMITTED, due_date=self.today - timedelta(days=1))
        self.peer_mission = RoadmapMission.objects.create(student=self.peer_student, title='Shortlist', status=RoadmapMission.Status.SUBMITTED)
        self.peer_document = Document.objects.create(student=self.peer_student, title='Passport', status=Document.Status.UPLOADED)
        self.peer_achievement = Achievement.objects.create(student=self.peer_student, title='Olympiad', category='olympiad', description='Gold')
        self.peer_log = ActivityLog.objects.create(actor=self.counselor_peer, student=self.peer_student, action='Peer only')

    def test_the_peers_students_are_not_counted_on_home(self):
        self.act_as(self.counselor)
        data = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(data['review'], {'tasks': 0, 'documents': 0, 'roadmap': 0, 'portfolio': 0, 'essays': 0})
        self.assertEqual(data['students_need_you'], 0)
        self.assertEqual(data['deadlines'], [])
        # The peer does see their own.
        self.act_as(self.counselor_peer)
        data = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(data['review'], {'tasks': 1, 'documents': 1, 'roadmap': 1, 'portfolio': 1, 'essays': 0})

    def test_the_peers_students_and_records_are_not_listed(self):
        self.act_as(self.counselor)
        self.assertNotIn(self.peer_student.pk, [row['id'] for row in self.results(self.client.get('/api/students/'))])
        for resource in ('tasks', 'roadmap-missions', 'documents', 'achievements', 'activity'):
            rows = self.results(self.client.get(f'/api/{resource}/?student={self.peer_student.pk}&cursor='))
            self.assertEqual(rows, [], resource)
        self.assertEqual(self.client.get(f'/api/students/{self.peer_student.pk}/').status_code, 404)

    def test_the_peers_work_cannot_be_sent_back_approved_or_reminded(self):
        self.act_as(self.counselor)
        records = (
            ('tasks', self.peer_task), ('roadmap-missions', self.peer_mission),
            ('documents', self.peer_document), ('achievements', self.peer_achievement),
        )
        for resource, record in records:
            response = self.client.post(f'/api/{resource}/{record.pk}/send-back/', {'note': 'Fix it'}, format='json')
            self.assertEqual(response.status_code, 404, f'send-back {resource}')
            response = self.client.post(f'/api/{resource}/{record.pk}/approve/', {'note': 'Fine'}, format='json')
            self.assertEqual(response.status_code, 404, f'approve {resource}')
        response = self.client.post(f'/api/students/{self.peer_student.pk}/remind/', {'topic': 'profile'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.peer_task.refresh_from_db()
        self.peer_document.refresh_from_db()
        self.peer_achievement.refresh_from_db()
        self.assertEqual(self.peer_task.status, Task.Status.SUBMITTED)
        self.assertEqual(self.peer_document.status, Document.Status.UPLOADED)
        self.assertFalse(self.peer_achievement.verified)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(XPTransaction.objects.exists())

    def test_the_peers_student_cannot_be_booked(self):
        self.act_as(self.counselor)
        response = self.client.post('/api/bookings/', {
            'student': self.peer_student.pk, 'topic': 'SAT plan',
            'starts_at': (timezone.now() + timedelta(days=3)).isoformat(), 'duration_minutes': 30,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Booking.objects.exists())


class ApprovalNoteValidationTests(WorkspaceBase):
    def test_a_too_long_note_approves_nothing(self):
        task = self.task(status=Task.Status.SUBMITTED)
        mission = RoadmapMission.objects.create(student=self.student, title='Shortlist', status=RoadmapMission.Status.SUBMITTED)
        self.act_as(self.counselor)
        for resource, record in (('tasks', task), ('roadmap-missions', mission)):
            response = self.client.post(f'/api/{resource}/{record.pk}/approve/', {'note': 'x' * 2001}, format='json')
            self.assertEqual(response.status_code, 400, resource)
        task.refresh_from_db()
        mission.refresh_from_db()
        self.assertEqual(task.status, Task.Status.SUBMITTED)
        self.assertEqual(mission.status, RoadmapMission.Status.SUBMITTED)
        self.assertFalse(XPTransaction.objects.exists())
