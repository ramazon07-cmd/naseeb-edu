"""Counselor Home: GET /api/dashboard/stats/?include=home and the check-in POST.

Each field is computed on the server over every assigned, active student, and
a counselor never sees another counselor's students in any of them.
"""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest import mock

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.counselor_summary import (
    CHECK_IN_OFF, CHECK_IN_ON, HISTORY_WEEKS, progress_bucket, week_of,
)
from apps.admissions.models import (
    Achievement, ActivityLog, Application, Booking, ChannelMembership, ChannelMessage, Document, MeetingNote, MessageChannel,
    RecommendationLetter, RoadmapMission, Task, University,
)
from apps.admissions.tenancy import set_student_active
from apps.users.models import User

from ..test_audit_base import AuditBaseMixin

URL = '/api/dashboard/stats/'
HOME_URL = f'{URL}?include=home'
WEDNESDAY = date(2026, 10, 7)


def at(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


class HomeBase(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.week = week_of(self.today)
        self._serial = 0
        self.student_user.first_name, self.student_user.last_name = 'Ramazon', 'Ergashev'
        self.student_user.save(update_fields=['first_name', 'last_name'])

    def new_student(self, first='Student', counselor=None, school=None):
        self._serial += 1
        school = school or self.school_a
        user = self.make_user(f'home-{self._serial}', User.Role.STUDENT, school, first_name=first)
        return self.make_profile(user, school, counselor or self.counselor)

    def home(self, user=None, day=None):
        self.client.force_authenticate(user or self.counselor)
        if day is None:
            response = self.client.get(HOME_URL)
        else:
            with mock.patch('django.utils.timezone.localdate', return_value=day):
                response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['home']

    def check_in(self, student, day, checked=True, user=None):
        self.client.force_authenticate(user or self.counselor)
        return self.client.post(URL, {'student': student.pk, 'date': day.isoformat(), 'checked': checked}, format='json')


class HomeShapeTests(HomeBase):
    def test_home_is_only_sent_when_asked_for(self):
        self.client.force_authenticate(self.counselor)
        self.assertNotIn('home', self.client.get(URL).data)
        home = self.home()
        self.assertEqual(set(home), {
            'today', 'week', 'review_items', 'need_you', 'meetings', 'messages', 'deadlines', 'check_ins',
            'check_in_history', 'progress',
        })
        self.assertEqual(home['today'], self.today.isoformat())
        self.assertEqual(len(home['week']), 7)
        self.assertEqual(date.fromisoformat(home['week'][0]).weekday(), 0)

    def test_other_roles_never_get_home(self):
        for user in (self.teacher, self.organization, self.admin, self.student_user):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertNotIn('home', self.client.get(HOME_URL).data)


class ReviewItemsTests(HomeBase):
    def test_oldest_first_across_kinds_with_the_review_page_ids(self):
        task = Task.objects.create(student=self.student, title='Essay draft', status=Task.Status.SUBMITTED,
                                   due_date=self.today, submitted_at=timezone.now() - timedelta(days=3))
        document = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x')
        Document.objects.filter(pk=document.pk).update(updated_at=timezone.now() - timedelta(days=5))
        RoadmapMission.objects.create(student=self.student, title='Baseline', status=RoadmapMission.Status.SUBMITTED)
        Achievement.objects.create(student=self.student, title='Sent back', category='olympiad', description='x',
                                   counselor_comment='More')
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        items = self.home()['review_items']
        self.assertEqual([item['id'] for item in items], [f'document-{document.pk}', f'task-{task.pk}'])
        self.assertEqual(items[0]['student_name'], 'Ramazon Ergashev')
        self.assertEqual(items[0]['record_id'], document.pk)

    def test_closed_roadmap_cannot_fill_the_visible_review_page(self):
        for index in range(10):
            RoadmapMission.objects.create(student=self.student, title=f'Hidden {index}', status=RoadmapMission.Status.SUBMITTED)
        RoadmapMission.objects.filter(student=self.student).update(updated_at=timezone.now() - timedelta(days=5))
        task = Task.objects.create(student=self.student, title='Visible task', status=Task.Status.SUBMITTED,
                                   due_date=self.today, submitted_at=timezone.now())
        self.assertEqual([item['id'] for item in self.home()['review_items']], [f'task-{task.pk}'])

    def test_another_counselors_work_is_not_listed(self):
        Task.objects.create(student=self.student_b, title='B', status=Task.Status.SUBMITTED, due_date=self.today)
        self.assertEqual(self.home()['review_items'], [])


class FilelessDocumentTests(HomeBase):
    """A document in a review status with no file and no link cannot be approved
    (DocumentViewSet.awaiting_review), so every count treats it as missing, not as review work."""

    def test_counted_as_missing_everywhere_and_waiting_nowhere(self):
        empty = Document.objects.create(student=self.student, title='Passport', status=Document.Status.UPLOADED)
        Document.objects.create(student=self.student, title='Visa', status=Document.Status.REVIEWING, file=None)
        filed = Document.objects.create(student=self.student, title='Transcript', status=Document.Status.UPLOADED,
                                        file='student_documents/transcript.pdf')
        self.client.force_authenticate(self.counselor)
        data = self.client.get(HOME_URL).data
        self.assertEqual(data['review']['documents'], 1)
        self.assertEqual(data['documents_pending_review'], 1)
        self.assertEqual([item['id'] for item in data['home']['review_items']], [f'document-{filed.pk}'])
        self.assertEqual(data['students_need_you'], 1)
        self.assertEqual(data['home']['need_you']['students'][0]['reasons'], [{'key': 'missing_document', 'count': 2, 'title': ''}])
        listed = self.client.get('/api/documents/', {'awaiting_review': 'true'}).data
        self.assertEqual([row['id'] for row in listed.get('results', listed)], [filed.pk])
        self.assertEqual(self.client.post(f'/api/documents/{empty.pk}/approve/', {}, format='json').status_code, 400)


class NeedYouTests(HomeBase):
    def test_reasons_are_computed_over_every_student_not_a_first_page(self):
        # 55 students sorted by name before the one who needs the counselor (bug #7: Home read the first 50).
        for _ in range(55):
            self.new_student(first='Aaron')
        late = self.new_student(first='Zarina')
        for index in range(4):
            Task.objects.create(student=late, title=f'T{index}', due_date=self.today - timedelta(days=2))
        for index in range(2):
            RoadmapMission.objects.create(student=late, title=f'M{index}', due_date=self.today - timedelta(days=1))
        Document.objects.create(student=late, title='IELTS certificate', status=Document.Status.REQUIRED)
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        Document.objects.create(student=self.student, title='Transcript', status=Document.Status.REQUIRED)
        Task.objects.create(student=self.student_b, title='Other', due_date=self.today - timedelta(days=9))

        need_you = self.home()['need_you']
        self.client.force_authenticate(self.counselor)
        self.assertEqual(need_you['total'], self.client.get(URL).data['students_need_you'])
        self.assertEqual(need_you['total'], 2)
        first = need_you['students'][0]
        self.assertEqual((first['id'], first['name']), (late.pk, 'Zarina'))
        self.assertEqual(first['reasons'], [
            {'key': 'late_task', 'count': 4},
            {'key': 'late_mission', 'count': 2},
            {'key': 'missing_document', 'count': 1, 'title': 'IELTS certificate'},
        ])
        # Two missing documents: a count, no single title.
        self.assertEqual(need_you['students'][1]['reasons'], [{'key': 'missing_document', 'count': 2, 'title': ''}])

    def test_deactivated_students_drop_out(self):
        gone = self.new_student(first='Gone')
        Task.objects.create(student=gone, title='Late', due_date=self.today - timedelta(days=3))
        set_student_active(gone, False, self.admin)
        self.assertEqual(self.home()['need_you'], {'total': 0, 'students': []})


class MeetingTests(HomeBase):
    def test_todays_meetings_and_the_days_of_the_week_that_have_some(self):
        today_meeting = Booking.objects.create(student=self.student, participant=self.counselor, topic='Essay',
                                               starts_at=at(self.today, 15), status=Booking.Status.APPROVED)
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Early', starts_at=at(self.today, 9))
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Cancelled',
                               starts_at=at(self.today, 11), status=Booking.Status.CANCELLED)
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Monday',
                               starts_at=at(self.week[0], 12), status=Booking.Status.COMPLETED)
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Next week',
                               starts_at=at(self.week[-1] + timedelta(days=1)))
        Booking.objects.create(student=self.student_b, participant=self.counselor_b, topic='Not mine', starts_at=at(self.today))
        meetings = self.home()['meetings']
        self.assertEqual([row['topic'] for row in meetings['today']], ['Early', 'Essay'] if self.today != self.week[0] else ['Early', 'Monday', 'Essay'])
        self.assertEqual(meetings['today'][-1]['id'], today_meeting.pk)
        self.assertEqual(meetings['today'][-1]['student_name'], 'Ramazon Ergashev')
        expected = {self.today.isoformat(): 2, self.week[0].isoformat(): 1}
        if self.today == self.week[0]:
            expected = {self.today.isoformat(): 3}
        self.assertEqual(meetings['days'], expected)


class MessageTests(HomeBase):
    def direct(self, *users):
        channel = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=self.school_a)
        for user in users:
            ChannelMembership.objects.create(channel=channel, user=user)
        return channel

    def test_unread_count_and_distinct_students(self):
        other_user = self.new_student(first='Abbos').user
        first, second, staff = self.direct(self.counselor, self.student_user), self.direct(self.counselor, other_user), \
            self.direct(self.counselor, self.teacher)
        for _ in range(3):
            ChannelMessage.objects.create(channel=first, sender=self.student_user, body='hi')
        ChannelMessage.objects.create(channel=second, sender=other_user, body='hello')
        ChannelMessage.objects.create(channel=staff, sender=self.teacher, body='staff')
        ChannelMessage.objects.create(channel=first, sender=self.counselor, body='mine')
        self.assertEqual(self.home()['messages'], {'unread': 5, 'students': 2})
        ChannelMembership.objects.filter(channel=first, user=self.counselor).update(last_read_at=timezone.now())
        self.assertEqual(self.home()['messages'], {'unread': 2, 'students': 1})


class DeadlineTests(HomeBase):
    def test_this_weeks_deadlines_stay_visible_behind_a_backlog(self):
        # Bug #6: ten old overdue tasks used to fill the card.
        for index in range(10):
            Task.objects.create(student=self.student, title=f'Old {index}', due_date=WEDNESDAY - timedelta(days=40 + index))
        Task.objects.create(student=self.student, title='Due Friday', due_date=WEDNESDAY + timedelta(days=2))
        RoadmapMission.objects.create(student=self.student, title='Due Monday', due_date=WEDNESDAY - timedelta(days=2))
        RoadmapMission.objects.create(student=self.student, title='No date')
        RecommendationLetter.objects.create(student=self.student, recommender_name='Next week',
                                            deadline=WEDNESDAY + timedelta(days=5))
        Task.objects.create(student=self.student_b, title='Not mine', due_date=WEDNESDAY)
        deadlines = self.home(day=WEDNESDAY)['deadlines']
        self.assertEqual([(row['title'], row['kind'], row['late']) for row in deadlines['items']],
                         [('Due Monday', 'mission', True), ('Due Friday', 'task', False)])
        self.assertEqual((deadlines['total'], deadlines['overdue']), (2, 10))
        self.assertTrue(all(row['due'] for row in deadlines['items']))


class CheckInTests(HomeBase):
    def days_of(self, home, student):
        return next(row['days'] for row in home['check_ins']['students'] if row['student'] == student.pk)

    def index(self, day):
        return (day - self.week[0]).days

    def test_days_come_from_the_counselors_own_work(self):
        abbos = self.new_student(first='Abbos')
        self.new_student(first='Akbar')
        # A meeting note and an approval on the same day count once; assigning the student does not count.
        MeetingNote.objects.create(student=self.student, counselor=self.counselor, title='Call', summary='x',
                                   meeting_date=self.week[0])
        ActivityLog.objects.create(actor=self.counselor, student=abbos, action='Document approved: Passport')
        ActivityLog.objects.create(actor=self.counselor, student=abbos, action='Student assigned to counselor: Firdavs')
        ActivityLog.objects.create(actor=self.counselor_peer, student=self.student, action='Task approved: x')
        Task.objects.create(student=self.student, title='Assigned', assigned_by=self.counselor, due_date=self.today)
        home = self.home()
        check_ins = home['check_ins']
        self.assertEqual((check_ins['students_total'], check_ins['checked_in']), (3, 2))
        self.assertEqual([row['name'] for row in check_ins['students']], ['Abbos', 'Akbar', 'Ramazon Ergashev'])
        ramazon = self.days_of(home, self.student)
        self.assertEqual(ramazon[0], 'auto')
        self.assertEqual(ramazon[self.index(self.today)], 'auto')
        self.assertEqual(self.days_of(home, abbos)[self.index(self.today)], 'auto')
        self.assertEqual(sum(1 for value in self.days_of(home, abbos) if value), 1)

    def test_meetings_held_and_direct_messages_count(self):
        # Already held, and still today: just after midnight "five minutes ago" is yesterday.
        held_at = max(timezone.now() - timedelta(minutes=5), at(timezone.localdate(), 0))
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Held',
                               starts_at=held_at, status=Booking.Status.APPROVED)
        later = self.new_student(first='Later')
        Booking.objects.create(student=later, participant=self.counselor, topic='Not yet',
                               starts_at=timezone.now() + timedelta(hours=2), status=Booking.Status.APPROVED)
        messaged = self.new_student(first='Messaged')
        channel = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=self.school_a)
        ChannelMembership.objects.create(channel=channel, user=self.counselor)
        ChannelMembership.objects.create(channel=channel, user=messaged.user)
        ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='How is the essay?')
        home = self.home()
        today = self.index(timezone.localdate())
        self.assertEqual(self.days_of(home, self.student)[today], 'auto')
        self.assertEqual(self.days_of(home, messaged)[today], 'auto')
        self.assertIsNone(self.days_of(home, later)[today])

    def test_tap_a_day_on_and_off(self):
        day = self.week[0]
        response = self.check_in(self.student, day)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.days_of(self.home(), self.student)[0], 'manual')
        self.assertEqual(self.home()['check_ins']['checked_in'], 1)
        self.assertEqual(self.check_in(self.student, day, checked=False).status_code, 200)
        self.assertIsNone(self.days_of(self.home(), self.student)[0])
        # Nothing is deleted: both taps stay in the student's timeline.
        self.assertEqual(
            list(ActivityLog.objects.filter(student=self.student).order_by('pk').values_list('action', 'metadata')),
            [(CHECK_IN_ON, {'event': 'counselor.check_in', 'date': day.isoformat()}),
             (CHECK_IN_OFF, {'event': 'counselor.check_in', 'date': day.isoformat()})],
        )

    def test_only_this_week_up_to_today(self):
        self.assertEqual(self.check_in(self.student, self.today + timedelta(days=1)).status_code, 400)
        self.assertEqual(self.check_in(self.student, self.week[0] - timedelta(days=1)).status_code, 400)
        self.assertFalse(ActivityLog.objects.exists())

    def test_only_the_students_own_counselor(self):
        self.assertEqual(self.check_in(self.student_b, self.today).status_code, 404)
        self.assertEqual(self.check_in(self.student, self.today, user=self.counselor_peer).status_code, 404)
        for user in (self.teacher, self.organization, self.admin, self.student_user):
            with self.subTest(user=user.username):
                self.assertEqual(self.check_in(self.student, self.today, user=user).status_code, 403)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(URL, {'student': self.student.pk}, format='json').status_code, 400)
        self.assertFalse(ActivityLog.objects.exists())

    def test_another_counselors_check_ins_are_not_mine(self):
        ActivityLog.objects.create(actor=self.counselor_b, student=self.student_b, action='Task approved: B')
        home = self.home()
        self.assertEqual([row['student'] for row in home['check_ins']['students']], [self.student.pk])
        self.assertEqual(home['check_ins']['checked_in'], 0)
        other = self.home(self.counselor_b)
        self.assertEqual([row['student'] for row in other['check_ins']['students']], [self.student_b.pk])


class ProgressTests(HomeBase):
    def test_bucket_rules(self):
        self.assertEqual(progress_bucket(50, 50, 0), 'on_track')
        self.assertEqual(progress_bucket(80, 50, 0), 'on_track')
        self.assertEqual(progress_bucket(40, 50, 0), 'behind')
        self.assertEqual(progress_bucket(90, 50, 1), 'behind')
        self.assertEqual(progress_bucket(90, 50, 3), 'needs_attention')
        self.assertEqual(progress_bucket(20, 50, 0), 'needs_attention')

    def test_buckets_and_lowest_progress_first(self):
        # Ramazon: 1 of 4 missions done though all 4 are past due (expected 100%) -> 25%, needs attention.
        RoadmapMission.objects.create(student=self.student, title='Done', status=RoadmapMission.Status.COMPLETED,
                                      due_date=self.today - timedelta(days=9))
        for index in range(3):
            RoadmapMission.objects.create(student=self.student, title=f'Late {index}', due_date=self.today - timedelta(days=2))
        # Abbos: 1 of 2 done, the other due later -> 50%, on track.
        abbos = self.new_student(first='Abbos')
        RoadmapMission.objects.create(student=abbos, title='Done', status=RoadmapMission.Status.COMPLETED)
        RoadmapMission.objects.create(student=abbos, title='Later', due_date=self.today + timedelta(days=9))
        # Akbar: 3 of 4 done, but a late task -> 75%, behind.
        akbar = self.new_student(first='Akbar')
        for index in range(3):
            RoadmapMission.objects.create(student=akbar, title=f'D{index}', status=RoadmapMission.Status.COMPLETED)
        RoadmapMission.objects.create(student=akbar, title='Open')
        Task.objects.create(student=akbar, title='Late task', due_date=self.today - timedelta(days=1))
        RoadmapMission.objects.create(student=self.student_b, title='Other', due_date=self.today - timedelta(days=2))

        progress = self.home()['progress']
        self.assertEqual(progress['total'], 3)
        self.assertEqual(progress['buckets'], {'on_track': 1, 'behind': 1, 'needs_attention': 1})
        self.assertEqual(
            [(row['name'], row['completion'], row['expected'], row['late'], row['bucket']) for row in progress['students']],
            [('Ramazon Ergashev', 25, 100, 3, 'needs_attention'), ('Abbos', 50, 0, 0, 'on_track'), ('Akbar', 75, 0, 1, 'behind')],
        )


class HomeCostTests(HomeBase):
    def test_queries_do_not_grow_with_the_roster(self):
        def add(count):
            for _ in range(count):
                student = self.new_student()
                Task.objects.create(student=student, title='Late', due_date=self.today - timedelta(days=1))
                RoadmapMission.objects.create(student=student, title='M', status=RoadmapMission.Status.SUBMITTED)
                Document.objects.create(student=student, title='D', status=Document.Status.REQUIRED)
                ActivityLog.objects.create(actor=self.counselor, student=student, action='Task approved: x')

        self.client.force_authenticate(self.counselor)
        add(3)
        few, _ = self.get_counted(HOME_URL)
        add(12)
        many, response = self.get_counted(HOME_URL)
        self.assertEqual(few, many)
        self.assertEqual(response.data['home']['need_you']['total'], 15)
        self.assertEqual(response.data['home']['check_ins']['checked_in'], 15)


class HomeContractTests(HomeBase):
    def test_home_response_is_a_superset_of_the_plain_stats(self):
        Task.objects.create(student=self.student, title='Late', due_date=self.today - timedelta(days=1))
        Task.objects.create(student=self.student, title='Sent', status=Task.Status.SUBMITTED, due_date=self.today)
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Soon',
                               starts_at=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(self.counselor)
        plain = self.client.get(URL).data
        cache.clear()
        with_home = self.client.get(HOME_URL).data
        self.assertEqual(set(with_home) - set(plain), {'home'})
        self.assertEqual({key: with_home[key] for key in plain}, dict(plain))
        self.assertEqual(with_home['students_need_you'], with_home['home']['need_you']['total'])
        self.assertEqual(with_home['home']['messages'], {
            'unread': with_home['badges']['messages_unread'], 'students': with_home['badges']['messages_unread_students'],
        })

    def test_deadlines_name_the_student_in_full(self):
        Task.objects.create(student=self.student, title='Due today', due_date=self.today)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(URL).data['deadlines'][0]['student_name'], 'Ramazon Ergashev')


class BadgeTests(HomeBase):
    def badges(self):
        self.client.force_authenticate(self.counselor)
        return self.client.get(URL).data['badges']

    def test_pending_meetings_like_the_bookings_page(self):
        # Booked by a student of the school who is not on this counselor's caseload: still theirs.
        peers = self.new_student(first='Peer', counselor=self.counselor_peer)
        Booking.objects.create(student=peers, participant=self.counselor, topic='Asked', starts_at=at(self.today + timedelta(days=2)))
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Asked too',
                               starts_at=at(self.today + timedelta(days=3)))
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Expired',
                               starts_at=timezone.now() - timedelta(hours=1))
        Booking.objects.create(student=self.student, participant=self.counselor, topic='Confirmed',
                               starts_at=at(self.today + timedelta(days=2)), status=Booking.Status.APPROVED)
        Booking.objects.create(student=self.student, participant=self.counselor_peer, topic='Not mine',
                               starts_at=at(self.today + timedelta(days=2)))
        # A booking with a student of another school (a counselor who moved on): the Bookings page hides it.
        Booking.objects.create(student=self.student_b, participant=self.counselor, topic='Old school',
                               starts_at=at(self.today + timedelta(days=2)))
        self.assertEqual(self.badges()['meetings_pending'], 2)
        listed = self.client.get('/api/bookings/?status=pending').data
        rows = listed.get('results', listed)
        self.assertEqual(sorted(row['topic'] for row in rows), ['Asked', 'Asked too', 'Expired'])

    def test_unread_messages_conversations_and_students(self):
        other = self.new_student(first='Abbos').user
        first = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=self.school_a)
        group = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='G', school=self.school_a)
        for channel, users in ((first, (self.counselor, self.student_user)), (group, (self.counselor, other, self.teacher))):
            for user in users:
                ChannelMembership.objects.create(channel=channel, user=user)
        ChannelMessage.objects.create(channel=first, sender=self.student_user, body='1')
        ChannelMessage.objects.create(channel=first, sender=self.student_user, body='2')
        ChannelMessage.objects.create(channel=group, sender=self.teacher, body='3')
        ChannelMessage.objects.create(channel=group, sender=self.counselor, body='mine')
        self.assertEqual(self.badges(), {
            'meetings_pending': 0, 'messages_unread': 3, 'messages_unread_conversations': 2, 'messages_unread_students': 1,
            'students_pending': 0,
        })
        channels = self.client.get('/api/message-channels/').data
        rows = channels.get('results', channels)
        self.assertEqual(sum(row['unread_count'] for row in rows), 3)
        self.assertEqual(sum(1 for row in rows if row['unread_count']), 2)

    def test_home_meetings_count_any_student_of_the_school(self):
        peers = self.new_student(first='Peer', counselor=self.counselor_peer)
        Booking.objects.create(student=peers, participant=self.counselor, topic='Peer', starts_at=at(self.today, 16),
                               status=Booking.Status.APPROVED)
        Booking.objects.create(student=self.student_b, participant=self.counselor, topic='Other school',
                               starts_at=at(self.today, 17), status=Booking.Status.APPROVED)
        meetings = self.home()['meetings']
        self.assertEqual([row['topic'] for row in meetings['today']], ['Peer'])
        self.assertEqual(meetings['today'][0]['student_name'], 'Peer')
        self.assertEqual(meetings['days'], {self.today.isoformat(): 1})


class CheckInPagingTests(HomeBase):
    def test_home_lists_fifty_students_needing_attention_first(self):
        for _ in range(54):
            self.new_student(first='Aaron')
        late = self.new_student(first='Zarina')
        Task.objects.create(student=late, title='Late', due_date=self.today - timedelta(days=1))
        ActivityLog.objects.create(actor=self.counselor, student=late, action='Task approved: x')
        check_ins = self.home()['check_ins']
        self.assertEqual((check_ins['students_total'], check_ins['checked_in']), (56, 1))
        self.assertEqual((check_ins['limit'], check_ins['offset'], len(check_ins['students'])), (50, 0, 50))
        self.assertEqual(check_ins['students'][0]['name'], 'Zarina')
        self.assertEqual(check_ins['students'][1]['name'], 'Aaron')

    def test_show_all_pages_through_the_caseload(self):
        for _ in range(4):
            self.new_student(first='Aaron')
        self.client.force_authenticate(self.counselor)
        seen = []
        for offset in (0, 2, 4):
            data = self.client.get(f'{URL}?check_ins=all&limit=2&offset={offset}').data
            self.assertEqual(set(data), {'check_ins'})
            self.assertEqual(data['check_ins']['students_total'], 5)
            seen += [row['student'] for row in data['check_ins']['students']]
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5)
        self.assertNotIn(self.student_b.pk, seen)
        for query in ('limit=0', 'limit=201', 'limit=x', 'offset=-1'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f'{URL}?check_ins=all&{query}').status_code, 400)

    def test_other_roles_ignore_check_ins_all(self):
        self.client.force_authenticate(self.teacher)
        self.assertIn('students_total', self.client.get(f'{URL}?check_ins=all').data)


class CheckInWriteTests(HomeBase):
    def test_a_tap_that_changes_nothing_writes_nothing(self):
        day = self.week[0]
        self.assertEqual(self.check_in(self.student, day, checked=False).status_code, 200)
        self.assertFalse(ActivityLog.objects.exists())
        self.check_in(self.student, day)
        self.check_in(self.student, day)
        self.check_in(self.student, day, checked=False)
        self.check_in(self.student, day, checked=False)
        self.assertEqual(list(ActivityLog.objects.order_by('pk').values_list('action', flat=True)), [CHECK_IN_ON, CHECK_IN_OFF])

    def test_taps_are_rate_limited(self):
        with mock.patch('apps.admissions.views.dashboard.CheckInThrottle.get_rate', return_value='2/minute'):
            codes = [self.check_in(self.student, self.week[0], checked=index % 2 == 0).status_code for index in range(3)]
            self.assertEqual(codes, [200, 200, 429])
            self.client.force_authenticate(self.counselor)
            self.assertEqual(self.client.get(URL).status_code, 200)


class HomeScaleTests(HomeBase):
    def add(self, count):
        for _ in range(count):
            student = self.new_student()
            Task.objects.create(student=student, title='Late', due_date=self.today - timedelta(days=1))
            Task.objects.create(student=student, title='Sent', status=Task.Status.SUBMITTED, due_date=self.today)
            RoadmapMission.objects.create(student=student, title='M', status=RoadmapMission.Status.SUBMITTED)
            Document.objects.create(student=student, title='D', status=Document.Status.REQUIRED)
            ActivityLog.objects.create(actor=self.counselor, student=student, action='Task approved: x')
            ActivityLog.objects.create(actor=self.counselor, student=student, action=CHECK_IN_ON,
                                       metadata={'event': 'counselor.check_in', 'date': self.today.isoformat()})
            Booking.objects.create(student=student, participant=self.counselor, topic='B',
                                   starts_at=timezone.now() + timedelta(hours=1))
            channel = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=self.school_a)
            ChannelMembership.objects.create(channel=channel, user=self.counselor)
            ChannelMembership.objects.create(channel=channel, user=student.user)
            ChannelMessage.objects.create(channel=channel, sender=student.user, body='hi')
            ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='hello')

    def counted(self, url):
        cache.clear()
        return self.get_counted(url)

    def test_query_count_is_the_same_for_5_and_60_students(self):
        self.client.force_authenticate(self.counselor)
        urls = (URL, HOME_URL, f'{URL}?check_ins=all&limit=200')
        self.add(4)  # plus self.student: 5
        few = {url: self.counted(url)[0] for url in urls}
        self.add(55)
        many = {url: self.counted(url) for url in urls}
        self.assertEqual(few, {url: count for url, (count, _) in many.items()})
        home = many[HOME_URL][1].data
        self.assertEqual(home['students_total'], 60)
        self.assertEqual(home['students_need_you'], 59)
        self.assertEqual(home['badges']['meetings_pending'], 59)
        self.assertEqual(home['badges']['messages_unread_students'], 59)
        self.assertEqual((home['home']['check_ins']['checked_in'], len(home['home']['check_ins']['students'])), (59, 50))
        self.assertEqual(len(many[f'{URL}?check_ins=all&limit=200'][1].data['check_ins']['students']), 60)


class TenantIsolationTests(HomeBase):
    """Two schools, two counselors each: no Home field shows another counselor's or school's data."""

    def populate(self, counselor, school, tag):
        student = self.new_student(first=f'{tag}-Student', counselor=counselor, school=school)
        Task.objects.create(student=student, title=f'{tag} late task', due_date=self.today - timedelta(days=1))
        Task.objects.create(student=student, title=f'{tag} due task', due_date=self.week[-1])
        Task.objects.create(student=student, title=f'{tag} sent task', status=Task.Status.SUBMITTED, due_date=self.today)
        RoadmapMission.objects.create(student=student, title=f'{tag} late mission', due_date=self.today - timedelta(days=1))
        RoadmapMission.objects.create(student=student, title=f'{tag} sent mission', status=RoadmapMission.Status.SUBMITTED)
        Document.objects.create(student=student, title=f'{tag} missing', status=Document.Status.REQUIRED)
        Document.objects.create(student=student, title=f'{tag} uploaded', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x')
        Achievement.objects.create(student=student, title=f'{tag} award', category='olympiad', description='x')
        RecommendationLetter.objects.create(student=student, recommender_name=f'{tag} recommender', deadline=self.week[-1])
        Booking.objects.create(student=student, participant=counselor, topic=f'{tag} meeting',
                               starts_at=timezone.now() + timedelta(hours=1))
        Booking.objects.create(student=student, participant=counselor, topic=f'{tag} held',
                               starts_at=timezone.now() - timedelta(minutes=1), status=Booking.Status.APPROVED)
        MeetingNote.objects.create(student=student, counselor=counselor, title=f'{tag} note', summary='x', meeting_date=self.today)
        ActivityLog.objects.create(actor=counselor, student=student, action=f'Task approved: {tag}')
        ActivityLog.objects.create(actor=counselor, student=student, action=CHECK_IN_ON,
                                   metadata={'event': 'counselor.check_in', 'date': self.week[0].isoformat()})
        channel = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=school)
        ChannelMembership.objects.create(channel=channel, user=counselor)
        ChannelMembership.objects.create(channel=channel, user=student.user)
        ChannelMessage.objects.create(channel=channel, sender=student.user, body=f'{tag} hi')
        ChannelMessage.objects.create(channel=channel, sender=counselor, body=f'{tag} hello')
        return student

    def test_no_cross_school_or_cross_caseload_data(self):
        counselor_b2 = self.make_user('home-counselor-b2', User.Role.COUNSELOR, self.school_b)
        self.student.delete()
        self.student_b.delete()
        staff = {
            'A1': (self.counselor, self.school_a), 'A2': (self.counselor_peer, self.school_a),
            'B1': (self.counselor_b, self.school_b), 'B2': (counselor_b2, self.school_b),
        }
        students = {tag: self.populate(counselor, school, tag) for tag, (counselor, school) in staff.items()}
        for tag, (counselor, _) in staff.items():
            with self.subTest(counselor=tag):
                cache.clear()
                self.client.force_authenticate(counselor)
                data = self.client.get(HOME_URL).data
                text = repr(data)
                for other in staff:
                    if other != tag:
                        self.assertNotIn(f'{other}-Student', text)
                        self.assertNotIn(f'{other} ', text)
                own = students[tag].pk
                home = data['home']
                self.assertEqual(data['students_total'], 1)
                self.assertEqual(data['students_need_you'], 1)
                self.assertEqual(data['review'], {'tasks': 1, 'documents': 1, 'roadmap': 1, 'portfolio': 1, 'essays': 0})
                # Late task + late mission (overdue on a Monday) + due task + letter.
                self.assertEqual(data['deadlines_week_total'] + data['deadlines_overdue'], 4)
                self.assertEqual(data['badges'], {
                    'meetings_pending': 1, 'messages_unread': 1, 'messages_unread_conversations': 1, 'messages_unread_students': 1,
                    'students_pending': 0,
                })
                self.assertEqual({row['student'] for row in home['review_items']}, {own})
                self.assertEqual([row['id'] for row in home['need_you']['students']], [own])
                self.assertLessEqual({row['student'] for row in home['meetings']['today']}, {own})
                self.assertEqual({row['student'] for row in home['deadlines']['items']}, {own})
                self.assertEqual([row['student'] for row in home['check_ins']['students']], [own])
                self.assertEqual(home['check_ins']['checked_in'], 1)
                self.assertEqual([row['id'] for row in home['progress']['students']], [own])
                page = self.client.get(f'{URL}?check_ins=all').data['check_ins']
                self.assertEqual([row['student'] for row in page['students']], [own])


class EssayReviewListTests(HomeBase):
    def reviewing(self, user, query=''):
        self.client.force_authenticate(user)
        listed = self.client.get(f'/api/essays/?status=reviewing{query}').data
        return [row['title'] for row in listed.get('results', listed)]

    def test_awaiting_review_leaves_out_deactivated_students_like_the_badge(self):
        from apps.admissions.models import Essay, StudentProfile

        gone = self.new_student(first='Gone')
        flagged = self.new_student(first='Flagged')
        Essay.objects.create(student=self.student, title='Mine', status='reviewing', shared_with_counselor=True)
        Essay.objects.create(student=gone, title='Gone', status='reviewing', shared_with_counselor=True)
        Essay.objects.create(student=flagged, title='Flagged', status='reviewing', shared_with_counselor=True)
        set_student_active(gone, False, self.admin)
        # Deactivated on the profile only: still in the counselor's scope, but not counted.
        StudentProfile.objects.filter(pk=flagged.pk).update(deactivated_at=timezone.now())

        self.assertEqual(self.reviewing(self.counselor), ['Mine'])
        self.assertEqual(self.client.get(URL).data['review']['essays'], 1)
        self.assertEqual(self.reviewing(self.admin), ['Mine'])
        # One student's own list still shows their essay.
        self.assertEqual(self.reviewing(self.admin, f'&student={gone.pk}'), ['Gone'])
        self.assertEqual(self.reviewing(self.counselor, f'&student={flagged.pk}'), ['Flagged'])


class CheckInHistoryTests(HomeBase):
    """The "Last 12 weeks" heatmap: students checked in per day, from the same sources as the week grid."""

    def test_students_per_day_over_twelve_weeks(self):
        other = self.new_student(first='Other')
        week = week_of(WEDNESDAY)
        eleven_weeks_ago = week[0] - timedelta(weeks=11)
        # Two kinds of work with one student on one day count once; a second student makes it two.
        MeetingNote.objects.create(student=self.student, counselor=self.counselor, title='Call', summary='x',
                                   meeting_date=eleven_weeks_ago)
        MeetingNote.objects.create(student=other, counselor=self.counselor, title='Call', summary='x',
                                   meeting_date=eleven_weeks_ago)
        log = ActivityLog.objects.create(actor=self.counselor, student=self.student, action='Task approved: x')
        ActivityLog.objects.filter(pk=log.pk).update(created_at=at(eleven_weeks_ago))
        # Too old for the grid, someone else's work, another counselor's student, a non-check-in row.
        MeetingNote.objects.create(student=self.student, counselor=self.counselor, title='Old', summary='x',
                                   meeting_date=eleven_weeks_ago - timedelta(days=1))
        MeetingNote.objects.create(student=self.student, counselor=self.counselor_peer, title='Peer', summary='x',
                                   meeting_date=week[1])
        MeetingNote.objects.create(student=self.student_b, counselor=self.counselor, title='B', summary='x',
                                   meeting_date=week[1])
        assigned = ActivityLog.objects.create(actor=self.counselor, student=other, action='Student assigned to counselor: x')
        ActivityLog.objects.filter(pk=assigned.pk).update(created_at=at(week[1]))
        # A tick this week (Monday), and a tick undone (Tuesday).
        for day, action in ((week[0], CHECK_IN_ON), (week[1], CHECK_IN_ON), (week[1], CHECK_IN_OFF)):
            row = ActivityLog.objects.create(actor=self.counselor, student=other, action=action,
                                             metadata={'event': 'counselor.check_in', 'date': day.isoformat()})
            ActivityLog.objects.filter(pk=row.pk).update(created_at=at(day, 9 if action == CHECK_IN_ON else 11))

        history = self.home(day=WEDNESDAY)['check_in_history']
        self.assertEqual(history['start'], eleven_weeks_ago.isoformat())
        self.assertEqual(history['end'], WEDNESDAY.isoformat())
        self.assertEqual(history['days'], {eleven_weeks_ago.isoformat(): 2, week[0].isoformat(): 1})
        self.assertEqual((week[-1] - eleven_weeks_ago).days + 1, HISTORY_WEEKS * 7)

    def test_tashkent_days(self):
        # 23:30 UTC on Tuesday is already Wednesday in Tashkent (UTC+5).
        day = WEDNESDAY
        log = ActivityLog.objects.create(actor=self.counselor, student=self.student, action='Document approved: x')
        ActivityLog.objects.filter(pk=log.pk).update(
            created_at=datetime.combine(day - timedelta(days=1), time(23, 30), tzinfo=dt_timezone.utc),
        )
        self.assertEqual(self.home(day=day)['check_in_history']['days'], {day.isoformat(): 1})

    def test_direct_messages_count_only_my_students(self):
        week = week_of(WEDNESDAY)
        other = self.new_student(first='Other')

        def message(kind, *users, day):
            channel = MessageChannel.objects.create(kind=kind, school=self.school_a)
            for user in users:
                ChannelMembership.objects.create(channel=channel, user=user)
            row = ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='Hi')
            ChannelMessage.objects.filter(pk=row.pk).update(created_at=at(day))

        message(MessageChannel.Kind.DIRECT, self.counselor, self.student_user, day=week[0])
        message(MessageChannel.Kind.DIRECT, self.counselor, other.user, day=week[0])
        message(MessageChannel.Kind.DIRECT, self.counselor, self.student_b.user, day=week[1])
        message(MessageChannel.Kind.DIRECT, self.counselor, self.teacher, day=week[1])
        message(MessageChannel.Kind.GROUP, self.counselor, self.student_user, other.user, day=week[2])
        self.assertEqual(self.home(day=WEDNESDAY)['check_in_history']['days'], {week[0].isoformat(): 2})

    def test_local_date_matches_trunc_date(self):
        from django.db.models.functions import TruncDate

        from apps.admissions.counselor_summary import _LocalDate

        # Tashkent (no DST), a negative fixed offset, and a window across a DST change (falls back to TruncDate).
        cases = (('Asia/Tashkent', date(2026, 10, 1)), ('America/Bogota', date(2026, 10, 1)),
                 ('America/New_York', date(2026, 10, 25)))
        for zone, start in cases:
            end = start + timedelta(days=13)
            with self.subTest(zone=zone), timezone.override(zone):
                ActivityLog.objects.all().delete()
                for offset in range(14):
                    for hour, minute in ((0, 0), (0, 1), (12, 0), (23, 59)):
                        moment = timezone.make_aware(datetime.combine(start + timedelta(days=offset), time(hour, minute)))
                        log = ActivityLog.objects.create(actor=self.counselor, student=self.student, action='x')
                        ActivityLog.objects.filter(pk=log.pk).update(created_at=moment)
                rows = ActivityLog.objects.order_by('pk')
                expected = list(rows.annotate(day=TruncDate('created_at')).values_list('day', flat=True))
                local = _LocalDate('created_at', start, end)
                self.assertEqual(local.offset is None, zone == 'America/New_York')
                self.assertEqual(list(rows.annotate(day=local).values_list('day', flat=True)), expected)
                self.assertEqual(len(set(expected)), 14)

    def test_queries_do_not_grow_with_the_roster(self):
        def add(count):
            for _ in range(count):
                student = self.new_student()
                MeetingNote.objects.create(student=student, counselor=self.counselor, title='n', summary='x',
                                           meeting_date=self.week[0] - timedelta(weeks=3))
                ActivityLog.objects.create(actor=self.counselor, student=student, action=CHECK_IN_ON,
                                           metadata={'event': 'counselor.check_in', 'date': self.today.isoformat()})

        self.client.force_authenticate(self.counselor)
        add(2)
        cache.clear()
        few, _ = self.get_counted(HOME_URL)
        add(10)
        cache.clear()
        many, response = self.get_counted(HOME_URL)
        self.assertEqual(few, many)
        days = response.data['home']['check_in_history']['days']
        self.assertEqual(days[self.today.isoformat()], 12)
        self.assertEqual(days[(self.week[0] - timedelta(weeks=3)).isoformat()], 12)


class SnapshotTests(HomeBase):
    """GET /api/dashboard/stats/?snapshot=<id>: one of the counselor's students, as they see their Home."""

    def snapshot(self, student_id, user=None, expected=200):
        self.client.force_authenticate(user or self.counselor)
        response = self.client.get(f'{URL}?snapshot={student_id}')
        self.assertEqual(response.status_code, expected, getattr(response, 'data', None))
        return response.data

    def test_real_fields_only(self):
        self.student.target_major = 'Computer Science'
        self.student.target_countries = 'Hong Kong, USA, '
        self.student.level = 2
        self.student.save(update_fields=['target_major', 'target_countries', 'level'])
        RoadmapMission.objects.create(student=self.student, title='Done', level=2, status=RoadmapMission.Status.COMPLETED)
        RoadmapMission.objects.create(student=self.student, title='Open', level=2)
        RoadmapMission.objects.create(student=self.student, title='Earlier', level=1, status=RoadmapMission.Status.COMPLETED)
        for index, status in enumerate(('researching', 'submitted', 'accepted')):
            university = University.objects.create(name=f'U{index}', country='USA')
            Application.objects.create(student=self.student, university=university, program='CS', status=status)
        Achievement.objects.create(student=self.student, title='Olympiad', category='olympiad', description='x')
        Task.objects.create(student=self.student, title='Far', due_date=self.today + timedelta(days=30))
        Task.objects.create(student=self.student, title='Soon', due_date=self.today + timedelta(days=2))
        Task.objects.create(student=self.student, title='Late', due_date=self.today - timedelta(days=1))
        Task.objects.create(student=self.student, title='Later', due_date=self.today + timedelta(days=9))
        Task.objects.create(student=self.student, title='Sent', status=Task.Status.SUBMITTED, due_date=self.today)

        data = self.snapshot(self.student.pk)['snapshot']
        self.assertEqual(data['name'], 'Ramazon Ergashev')
        self.assertEqual(data['study_goal'], 'Computer Science')
        self.assertEqual(data['target_countries'], ['Hong Kong', 'USA'])
        self.assertEqual((data['level'], data['stars']), (2, 2))
        self.assertEqual(data['roadmap'], {'percent': 67, 'approved': 2, 'total': 3, 'level_approved': 1, 'level_total': 2})
        self.assertEqual(data['applications'], {'total': 3, 'submitted': 2, 'accepted': 1})
        self.assertEqual(data['achievements'], 1)
        self.assertEqual(data['open_tasks'], 4)
        self.assertEqual([item['title'] for item in data['priorities']], ['Late', 'Soon', 'Later'])
        self.assertTrue(data['priorities'][0]['late'])

    def test_blank_goal_is_left_out(self):
        data = self.snapshot(self.student.pk)['snapshot']
        self.assertNotIn('study_goal', data)
        self.assertNotIn('target_countries', data)
        self.assertEqual(data['priorities'], [])

    def test_only_the_counselors_own_active_students(self):
        peer_student = self.new_student(first='Peer', counselor=self.counselor_peer)
        gone = self.new_student(first='Gone')
        set_student_active(gone, False, actor=self.counselor)
        for student_id in (self.student_b.pk, peer_student.pk, gone.pk, 999999):
            with self.subTest(student=student_id):
                self.snapshot(student_id, expected=404)
        self.snapshot('abc', expected=400)
        # Another school's counselor cannot read this school's student either.
        self.snapshot(self.student.pk, user=self.counselor_b, expected=404)

    def test_other_roles_get_plain_stats(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get(f'{URL}?snapshot={self.student.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('snapshot', response.data)

    def test_queries_do_not_grow_with_the_students_records(self):
        self.client.force_authenticate(self.counselor)
        few, _ = self.get_counted(f'{URL}?snapshot={self.student.pk}')
        for index in range(8):
            Task.objects.create(student=self.student, title=f'T{index}', due_date=self.today)
            RoadmapMission.objects.create(student=self.student, title=f'M{index}')
            Achievement.objects.create(student=self.student, title=f'A{index}', category='olympiad', description='x')
        many, response = self.get_counted(f'{URL}?snapshot={self.student.pk}')
        self.assertEqual(few, many)
        self.assertEqual(len(response.data['snapshot']['priorities']), 3)
