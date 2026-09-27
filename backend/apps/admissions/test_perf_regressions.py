"""Regression tests for the fixes found by the load test (scripts/loadtest/).

Each test pins down the cost of one hot endpoint: its query count, the SQL
shape that made it slow, or the size of its response.
"""
from datetime import date, timedelta

from django.db import connection
from django.utils import timezone
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions.models import (
    ChannelMembership, Essay, EssayRevision, EssayTab, MessageChannel, OpportunityProgram, ScreenTimeDaily, StudentProfile,
    Task, University,
)
from apps.users.models import User

from .test_audit_base import AuditBaseMixin


class ChannelListCostTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.community = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Everyone', school=self.school_a, is_public=True,
        )
        ChannelMembership.objects.create(channel=self.community, user=self.counselor, role='owner')
        for index in range(30):
            user = self.make_user(f'perf-member-{index}', User.Role.STUDENT, self.school_a)
            StudentProfile.objects.create(user=user, school=self.school_a, assigned_counselor=self.counselor)
            ChannelMembership.objects.create(channel=self.community, user=user)
        self.direct = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, direct_key='x', school=self.school_a)
        ChannelMembership.objects.create(channel=self.direct, user=self.counselor, role='owner')
        ChannelMembership.objects.create(channel=self.direct, user=self.student_user)

    def list_channels(self, user):
        self.client.force_authenticate(user)
        with CaptureQueriesContext(connection) as context:
            response = self.client.get('/api/message-channels/')
        self.assertEqual(response.status_code, 200)
        return response, [query['sql'] for query in context.captured_queries]

    def test_counselor_scope_does_not_join_students_or_need_distinct(self):
        # Joining the counselor's students multiplied every public channel by
        # the school's roster (3.7 s per request with 250 students).
        response, queries = self.list_channels(self.counselor)
        self.assertEqual(response.data['count'], 2)
        for sql in queries:
            self.assertNotIn('SELECT DISTINCT', sql)
            self.assertNotRegex(sql, r'JOIN "admissions_studentprofile"')

    def test_only_own_and_direct_memberships_are_loaded(self):
        response, queries = self.list_channels(self.counselor)
        by_id = {channel['id']: channel for channel in response.data['results']}
        self.assertEqual(by_id[self.community.id]['members_count'], 31)
        self.assertEqual(by_id[self.community.id]['my_role'], 'owner')
        self.assertEqual(by_id[self.direct.id]['display_name'], self.student_user.username)
        self.assertEqual(by_id[self.direct.id]['members_count'], 2)
        with connection.cursor() as cursor:
            membership_query = next(sql for sql in queries if sql.startswith('SELECT "admissions_channelmembership"."id"'))
            cursor.execute(f'SELECT COUNT(*) FROM ({membership_query}) AS loaded')
            # Counselor's two memberships plus the student's side of the direct chat.
            self.assertEqual(cursor.fetchone()[0], 3)

    def test_student_sees_public_school_channel_without_membership(self):
        response, _ = self.list_channels(self.student_user)
        ids = {channel['id'] for channel in response.data['results']}
        self.assertEqual(ids, {self.community.id, self.direct.id})
        community = next(channel for channel in response.data['results'] if channel['id'] == self.community.id)
        self.assertFalse(community['is_member'])
        self.assertEqual(community['members_count'], 31)


class LegacyEssayListCostTests(AuditBaseMixin, APITestCase):
    def add_essays(self, count):
        for index in range(count):
            essay = Essay.objects.create(
                student=self.student, title=f'Essay {index}', content='Some words here.', shared_with_counselor=True,
            )
            EssayTab.objects.create(
                essay=essay, title='Tab 1', content='Some words here.',
                doc={'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'x' * 5000}]}]},
            )
            for version in (1, 2):
                EssayRevision.objects.create(
                    essay=essay, version=version, prompt='', content='Some words here.', status='draft',
                    created_by=self.counselor,
                )

    def test_revisions_and_authors_are_prefetched(self):
        self.client.force_authenticate(self.counselor)
        self.add_essays(2)
        few, _ = self.get_counted('/api/essays/')
        self.add_essays(6)
        many, response = self.get_counted('/api/essays/')
        self.assertEqual(few, many)
        self.assertLessEqual(many, 5)
        first = response.data['results'][0]
        self.assertEqual([revision['version'] for revision in first['revisions']], [2, 1])
        self.assertEqual(first['revisions'][0]['created_by_name'], self.counselor.get_full_name())
        # History shows versions only; the text of every old draft is not sent.
        self.assertEqual(
            set(first['revisions'][0]),
            {'id', 'essay', 'version', 'status', 'created_by', 'created_by_name', 'created_at'},
        )

    def test_rich_doc_is_not_loaded(self):
        self.add_essays(1)
        self.client.force_authenticate(self.counselor)
        with CaptureQueriesContext(connection) as context:
            self.client.get('/api/essays/')
        # The tabs' rich docs live in their own table, which the legacy list never reads.
        self.assertTrue(any('"admissions_essay"' in query['sql'] for query in context.captured_queries))
        self.assertFalse(any('admissions_essaytab' in query['sql'] for query in context.captured_queries))


class ListPageSizeTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        Task.objects.bulk_create([
            Task(student=self.student, title=f'Task {index}', due_date=date(2027, 1, 1)) for index in range(230)
        ])
        self.client.force_authenticate(self.counselor)

    def test_default_page_is_unchanged(self):
        response = self.client.get('/api/tasks/')
        self.assertEqual(len(response.data['results']), 25)
        self.assertEqual(response.data['count'], 230)

    def test_next_links_keep_the_page_size(self):
        first = self.client.get('/api/tasks/?page_size=100')
        self.assertEqual(len(first.data['results']), 100)
        self.assertIn('page_size=100', first.data['next'])
        third = self.client.get(self.client.get(first.data['next']).data['next'])
        self.assertEqual(len(third.data['results']), 30)
        self.assertIsNone(third.data['next'])

    def test_page_size_is_capped(self):
        response = self.client.get('/api/tasks/?page_size=100000')
        self.assertEqual(len(response.data['results']), 100)


class CatalogCacheTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.harvard = University.objects.create(name='Harvard', country='USA')
        self.client.force_authenticate(self.student_user)

    def names(self, response):
        return [row['name'] for row in response.data['results']]

    def test_second_sign_in_is_served_from_the_cache(self):
        first, response = self.get_counted('/api/universities/?page_size=200')
        second, cached = self.get_counted('/api/universities/?page_size=200')
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(cached.data, response.data)

    def test_edits_show_up_immediately(self):
        self.client.get('/api/universities/')
        University.objects.create(name='Yale', country='USA')
        self.assertEqual(self.names(self.client.get('/api/universities/')), ['Harvard', 'Yale'])
        self.harvard.delete()
        self.assertEqual(self.names(self.client.get('/api/universities/')), ['Yale'])

    def test_pages_are_cached_separately(self):
        for index in range(30):
            OpportunityProgram.objects.create(title=f'P{index:02}', provider='x', program_type='international', category='c')
        first = self.client.get('/api/opportunity-programs/')
        full = self.client.get('/api/opportunity-programs/?page_size=100')
        self.assertEqual(len(first.data['results']), 25)
        self.assertEqual(len(full.data['results']), min(100, full.data['count']))
        self.assertGreater(len(full.data['results']), 25)

    def test_permissions_still_apply(self):
        self.client.get('/api/universities/')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/universities/').status_code, 401)


class ScreenTimeTrackCostTests(AuditBaseMixin, APITestCase):
    def test_a_batch_is_one_upsert(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        ScreenTimeDaily.objects.create(user=self.student_user, date=today, page='roadmap', active_seconds=100, sessions=3)
        self.client.force_authenticate(self.student_user)
        entries = [
            {'date': today.isoformat(), 'page': 'roadmap', 'seconds': 30},
            {'date': today.isoformat(), 'page': 'essay_lab', 'seconds': 45},
            {'date': yesterday.isoformat(), 'page': 'roadmap', 'seconds': 10},
        ]
        with self.assertNumQueries(1):
            response = self.client.post('/api/screen-time/track/', {'entries': entries}, format='json')
        self.assertEqual(response.data, {'tracked_seconds': 85, 'entries': 3})
        rows = {
            (row.date, row.page): (row.active_seconds, row.sessions)
            for row in ScreenTimeDaily.objects.filter(user=self.student_user)
        }
        self.assertEqual(rows, {
            (today, 'roadmap'): (130, 4),
            (today, 'essay_lab'): (45, 1),
            (yesterday, 'roadmap'): (10, 1),
        })


class AccountListCostTests(AuditBaseMixin, APITestCase):
    def add_students(self, first, count):
        for index in range(first, first + count):
            user = self.make_user(f'perf-account-{index}', User.Role.STUDENT, self.school_a)
            self.make_profile(user, self.school_a, self.counselor)

    def test_profiles_and_credentials_are_not_loaded_per_row(self):
        for account in (self.admin, self.organization, self.counselor):
            with self.subTest(role=account.role):
                self.client.force_authenticate(account)
                self.add_students(len(User.objects.all()), 3)
                few, _ = self.get_counted('/api/users/accounts/?page_size=200')
                self.add_students(len(User.objects.all()), 9)
                many, response = self.get_counted('/api/users/accounts/?page_size=200')
                self.assertEqual(few, many)
                self.assertLessEqual(many, 4)
                self.assertGreaterEqual(len(response.data['results']), 12)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudentUsernameAllocationTests(AuditBaseMixin, APITestCase):
    def create(self, full_name='Ali Valiyev'):
        from apps.admissions.tenancy import create_student_account

        return create_student_account(
            school=self.school_a, full_name=full_name, password='StrongPass123!', created_by=self.counselor,
        )

    def test_many_students_with_one_name_all_get_accounts(self):
        names = [self.create().user.username for _ in range(60)]
        self.assertEqual(names[:3], ['ali-valiyev', 'ali-valiyev2', 'ali-valiyev3'])
        self.assertEqual(names[-1], 'ali-valiyev60')
        self.assertEqual(len(set(names)), 60)

    def test_query_count_does_not_grow_with_taken_names(self):
        def counted():
            with CaptureQueriesContext(connection) as context:
                self.create()
            return len(context.captured_queries)

        early = counted()
        for _ in range(50):
            self.create()
        self.assertEqual(counted(), early)

    def test_the_lowest_free_number_is_reused(self):
        for _ in range(4):
            self.create()
        User.objects.filter(username='ali-valiyev3').delete()
        self.assertEqual(self.create().user.username, 'ali-valiyev3')
        self.assertEqual(self.create().user.username, 'ali-valiyev5')

    def test_other_names_with_the_same_prefix_are_ignored(self):
        for username in ('ali-valiyevich', 'ali-valiyev-2', 'Ali-Valiyev', 'ali-valiyev07'):
            self.make_user(username, User.Role.STUDENT, self.school_a)
        self.assertEqual(self.create().user.username, 'ali-valiyev')
        self.assertEqual(self.create().user.username, 'ali-valiyev2')

    def test_a_name_lost_to_a_concurrent_create_falls_back_to_a_random_suffix(self):
        from unittest import mock

        self.create()
        with mock.patch('apps.admissions.tenancy._free_username', return_value='ali-valiyev'):
            profile = self.create()
        self.assertRegex(profile.user.username, r'^ali-valiyev-[0-9a-f]{6}$')
        self.assertEqual(User.objects.filter(first_name='Ali').count(), 2)
