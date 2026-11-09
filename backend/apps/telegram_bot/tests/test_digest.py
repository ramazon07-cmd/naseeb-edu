from datetime import datetime, timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.admissions.models import (
    Achievement, Activity, Application, Document, Essay, EssayWritingDay, School, University,
)
from apps.telegram_bot import activity, digest
from apps.telegram_bot.activity import ActivityResult, EssayActivity

from .base import BotTestCase, make_student


class ActivityAdapterTests(TestCase):
    def test_reads_words_and_streak_from_writing_days(self):
        a = make_student('act_a', School.objects.create(name='Act School'))
        b = make_student('act_b', a.school)
        today = datetime(2026, 11, 8).date()
        for offset, met in ((0, True), (1, True), (2, True), (4, True)):
            EssayWritingDay.objects.create(user=a.user, date=today - timedelta(days=offset),
                                           words_net=120, words_peak=120 + offset, goal_met=met)
        EssayWritingDay.objects.create(user=b.user, date=today, words_net=30, words_peak=30, goal_met=False)
        result = activity.essay_activity_for([a.user_id, b.user_id, 999999], today)
        self.assertEqual(result.for_user(a.user_id), EssayActivity(words_today=120, streak_days=3))
        self.assertEqual(result.for_user(b.user_id), EssayActivity(words_today=30, streak_days=0))
        self.assertEqual(result.for_user(999999), EssayActivity(words_today=0, streak_days=0))

    def test_result_exposes_per_user_numbers(self):
        result = ActivityResult({7: EssayActivity(words_today=120, streak_days=4)})
        self.assertEqual(result.for_user(7).streak_days, 4)
        self.assertEqual(result.for_user(8), EssayActivity())


class DigestContentTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.chat = self.link(self.c1)

    def digest(self):
        response = self.post('digest', {'chat_id': self.chat})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def by_name(self, body, name):
        return next(item for item in body['students'] if item['name'] == name)

    def test_essays_count_edited_today_and_only_shared_ones(self):
        now = timezone.now()
        Essay.objects.create(student=self.s1, title='Shared today', shared_with_counselor=True, last_edited_at=now)
        Essay.objects.create(student=self.s1, title='Shared old', shared_with_counselor=True,
                             last_edited_at=now - timedelta(days=3))
        Essay.objects.create(student=self.s1, title='Private', shared_with_counselor=False, last_edited_at=now)
        Essay.objects.create(student=self.s1, title='Trashed', shared_with_counselor=True, trashed_at=now)
        item = self.by_name(self.digest(), 'Stu1 Tester')
        self.assertEqual(item['essays'], {'total': 2, 'edited_today': 1, 'words_today': 0})

    def share_essay(self, student):
        Essay.objects.create(student=student, title='Shared', shared_with_counselor=True)

    def test_streak_without_writing_days_is_zero_once_an_essay_is_shared(self):
        self.share_essay(self.s1)
        body = self.digest()
        self.assertEqual(self.by_name(body, 'Stu1 Tester')['streak'], {'days': 0, 'shared': True})

    def test_streak_and_words_are_hidden_for_students_without_a_shared_essay(self):
        today = timezone.localdate()
        EssayWritingDay.objects.create(user=self.s1.user, date=today, words_net=140, words_peak=140, goal_met=True)
        Essay.objects.create(student=self.s1, title='Private', shared_with_counselor=False)
        item = self.by_name(self.digest(), 'Stu1 Tester')
        self.assertEqual(item['streak'], {'days': None, 'shared': False})
        self.assertIsNone(item['essays']['words_today'])

    def test_streak_numbers_flow_through_for_shared_students(self):
        self.share_essay(self.s1)
        fake = ActivityResult({self.s1.user_id: EssayActivity(words_today=250, streak_days=6)})
        with mock.patch.object(digest, 'essay_activity_for', return_value=fake) as patched:
            body = self.digest()
        item = self.by_name(body, 'Stu1 Tester')
        self.assertEqual(patched.call_args.args[0], [self.s1.user_id])
        self.assertEqual(item['streak'], {'days': 6, 'shared': True})
        self.assertEqual(item['essays']['words_today'], 250)
        self.assertIsNone(self.by_name(body, 'Stu2 Tester')['essays']['words_today'])

    def test_activity_is_not_queried_when_essays_and_streak_are_off(self):
        self.share_essay(self.s1)
        with mock.patch.object(digest, 'essay_activity_for') as patched:
            digest.build_digest(self.c1, {'essays': False, 'streak': False, 'application': True})
        patched.assert_not_called()

    def test_application_section_counts_and_percent(self):
        Activity.objects.create(student=self.s1, name='Debate club', activity_type='club')
        Achievement.objects.create(student=self.s1, title='Olympiad', category='olympiad', description='won')
        university = University.objects.create(name='Uni', country='Testland')
        Application.objects.create(student=self.s1, university=university, program='CS')
        Document.objects.create(student=self.s1, title='Passport', document_type='passport')
        item = self.by_name(self.digest(), 'Stu1 Tester')['application']
        self.assertEqual(item['activities'], 1)
        self.assertEqual(item['honors'], 1)
        self.assertEqual(item['applications'], {'done': 0, 'total': 1})
        self.assertEqual(item['documents']['total'], 1)
        self.assertTrue(item['sections']['activities'])
        self.assertTrue(item['sections']['honors'])
        self.assertFalse(item['sections']['personal'])
        # 2 of the 12 profile readiness items (activities, honors): the website's own formula.
        self.assertEqual(item['percent'], 17)
        self.assertEqual(set(item['sections']), {'personal', 'academics', 'tests', 'goal', 'activities', 'honors'})

    def test_percent_matches_the_websites_profile_readiness(self):
        from apps.admissions.onboarding import profile_readiness
        from apps.admissions.progress import attach_progress_stats

        profile = attach_progress_stats([self.s2])[0]
        item = self.by_name(self.digest(), 'Stu2 Tester')['application']
        self.assertEqual(item['percent'], profile_readiness(profile)['percent'])

    def test_students_are_grouped_by_grade(self):
        body = self.post('students', {'chat_id': self.chat}).json()
        self.assertEqual(body['groups'], [
            {'grade': '9', 'count': 1, 'students': ['Stu1 Tester']},
            {'grade': '10', 'count': 1, 'students': ['Stu2 Tester']},
        ])

    def test_student_without_a_grade_gets_the_empty_group_last(self):
        make_student('stu6', self.school_a, self.c1, grade='')
        make_student('stu7', self.school_a, self.c1, grade='11')
        groups = self.post('students', {'chat_id': self.chat}).json()['groups']
        self.assertEqual([g['grade'] for g in groups], ['9', '10', '11', ''])


class DigestQueryBoundTests(BotTestCase):
    added = 0

    def count_for(self, extra):
        self.added += extra
        for i in range(extra):
            student = make_student(f'bulk{extra}-{i}', self.school_a, self.c1, grade=str(5 + i % 6))
            Essay.objects.create(student=student, title='E', shared_with_counselor=True, last_edited_at=timezone.now())
            Achievement.objects.create(student=student, title='A', category='sport', description='d')
        chat = self.link(self.c1)
        with CaptureQueriesContext(connection) as queries:
            response = self.post('digest', {'chat_id': chat})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_students'], 2 + self.added)
        return len(queries)

    def test_activity_is_read_with_one_query(self):
        a = make_student('one_q', School.objects.create(name='One Q School'))
        today = datetime(2026, 11, 8).date()
        EssayWritingDay.objects.create(user=a.user, date=today, words_net=120, words_peak=120, goal_met=True)
        with CaptureQueriesContext(connection) as queries:
            activity.essay_activity_for([a.user_id], today)
        self.assertEqual(len(queries), 1)

    def test_query_count_does_not_grow_with_students(self):
        small = self.count_for(1)
        large = self.count_for(30)
        self.assertEqual(small, large)
        self.assertLessEqual(large, 16)

    def test_a_capped_response_reports_the_true_total_and_the_omitted_count(self):
        for i in range(4):
            make_student(f'capped{i}', self.school_a, self.c1)
        chat = self.link(self.c1)
        with mock.patch.object(digest, 'MAX_STUDENTS', 3):
            body = self.post('digest', {'chat_id': chat}).json()
            listing = self.post('students', {'chat_id': chat}).json()
        total = body['total_students']
        self.assertGreater(total, 3)
        self.assertEqual(len(body['students']), 3)
        self.assertEqual(body['omitted'], total - 3)
        self.assertEqual(listing['total'], total)
        self.assertEqual(listing['omitted'], total - 3)
        self.assertEqual(sum(group['count'] for group in listing['groups']), 3)

    def test_an_uncapped_response_omits_nobody(self):
        chat = self.link(self.c1)
        self.assertEqual(self.post('digest', {'chat_id': chat}).json()['omitted'], 0)

    def test_student_list_is_one_student_query(self):
        for i in range(20):
            make_student(f'many{i}', self.school_a, self.c1)
        chat = self.link(self.c1)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.post('students', {'chat_id': chat}).status_code, 200)
        self.assertLessEqual(len(queries), 6)
