"""Smoke tests for every management command in backend/apps/*/management/commands/.

None of the commands should touch the network; every test runs with outbound
Python sockets blocked so an accidental HTTP call fails loudly instead of
reaching the internet. (psycopg talks to PostgreSQL through libpq, not Python
sockets, so the test database keeps working.)
"""
import socket
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.admissions.models import (
    Application, Document, Notification, ScreenTimeDaily, StudentProfile, Task, University, UniversityProgram,
)
from apps.users.models import User

from .test_audit_base import AuditBaseMixin

FAST_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


def _no_network(*args, **kwargs):
    raise AssertionError('Management commands must not open network connections.')


class NoNetworkMixin:
    def setUp(self):
        super().setUp()
        for target in ('socket.socket.connect', 'socket.socket.connect_ex', 'socket.create_connection'):
            patcher = mock.patch(target, side_effect=_no_network)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def run_command(*args, **kwargs):
        out = StringIO()
        call_command(*args, stdout=out, stderr=StringIO(), **kwargs)
        return out.getvalue()


class NetworkGuardTests(NoNetworkMixin, TestCase):
    def test_guard_is_active(self):
        with self.assertRaises(AssertionError):
            socket.create_connection(('example.com', 80))


class AuditCounselorSchoolsCommandTests(NoNetworkMixin, AuditBaseMixin, TestCase):
    def test_clean_database_passes(self):
        self.assertIn('Counselor-school audit passed.', self.run_command('audit_counselor_schools', '--fail-on-issues'))

    def test_reports_mismatched_links(self):
        # (A counselor without a school -- the MISSING branch -- is now blocked
        # by the counselor_requires_school DB constraint, so only MISMATCH can occur.)
        self.student_b.assigned_counselor = self.counselor  # school B student, school A counselor
        self.student_b.save(update_fields=['assigned_counselor'])
        output = self.run_command('audit_counselor_schools')
        self.assertNotIn('MISSING', output)
        self.assertIn(
            f'MISMATCH student={self.student_b.id} counselor={self.counselor.id} '
            f'student_school={self.school_b.id} counselor_school={self.school_a.id}',
            output,
        )
        self.assertIn('found 1 issue(s)', output)
        with self.assertRaisesMessage(CommandError, 'found 1 issue(s)'):
            self.run_command('audit_counselor_schools', '--fail-on-issues')


class GenerateNotificationsCommandTests(NoNetworkMixin, AuditBaseMixin, TestCase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        university = University.objects.create(name='Deadline U', country='USA')
        Task.objects.create(student=self.student, title='Late', due_date=today - timedelta(days=2), status='todo')
        Task.objects.create(student=self.student, title='Done', due_date=today - timedelta(days=2), status='approved')
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        Application.objects.create(
            student=self.student, university=university, program='CS', status='applying',
            deadline=today + timedelta(days=5),
        )
        # Nothing actionable for student B: approved task, submitted application, far deadline.
        Task.objects.create(student=self.student_b, title='Old', due_date=today - timedelta(days=9), status='approved')
        Application.objects.create(
            student=self.student_b, university=university, program='CS', status='submitted',
            deadline=today + timedelta(days=3),
        )
        Application.objects.create(
            student=self.student_b, university=university, program='Math', status='applying',
            deadline=today + timedelta(days=60),
        )

    def test_creates_one_notification_per_condition_and_is_idempotent(self):
        output = self.run_command('generate_notifications')
        self.assertIn('Generated or refreshed 3 notifications.', output)
        titles = set(Notification.objects.filter(student=self.student).values_list('title', flat=True))
        self.assertEqual(titles, {
            'Late tasks require attention', 'Required documents are missing', 'University deadline approaching',
        })
        self.assertFalse(Notification.objects.filter(student=self.student_b).exists())
        deadline = Notification.objects.get(title='University deadline approaching')
        self.assertIn('Deadline U deadline is', deadline.message)

        Notification.objects.update(is_read=True)
        self.run_command('generate_notifications')
        self.assertEqual(Notification.objects.count(), 3)
        self.assertFalse(Notification.objects.filter(is_read=True).exists())

    def test_empty_database_is_fine(self):
        StudentProfile.objects.all().delete()
        self.assertIn('Generated or refreshed 0 notifications.', self.run_command('generate_notifications'))


class LoadUniversityCatalogCommandTests(NoNetworkMixin, TestCase):
    def test_loads_catalog_idempotently_without_network(self):
        self.assertIn('Loaded', self.run_command('load_university_catalog'))
        counts = (University.objects.count(), UniversityProgram.objects.count())
        self.assertGreater(counts[0], 0)
        self.run_command('load_university_catalog')
        self.assertEqual((University.objects.count(), UniversityProgram.objects.count()), counts)


class PurgeScreenTimeCommandTests(NoNetworkMixin, AuditBaseMixin, TestCase):
    def add_row(self, days_ago, page='home'):
        return ScreenTimeDaily.objects.create(
            user=self.student_user, date=timezone.localdate() - timedelta(days=days_ago), page=page,
            active_seconds=60, sessions=1,
        )

    @override_settings(SCREEN_TIME_RETENTION_DAYS=30)
    def test_default_retention_is_used_when_no_days_given(self):
        # --days defaults to SCREEN_TIME_RETENTION_DAYS (read when the parser is built).
        old, recent = self.add_row(100), self.add_row(10)
        output = self.run_command('purge_screen_time')
        self.assertIn('Deleted 1 screen-time rows', output)
        self.assertFalse(ScreenTimeDaily.objects.filter(pk=old.pk).exists())
        self.assertTrue(ScreenTimeDaily.objects.filter(pk=recent.pk).exists())

    def test_days_option_and_lower_bound(self):
        keep_today, one_day, older = self.add_row(0), self.add_row(1), self.add_row(5)
        self.run_command('purge_screen_time', '--days', '3')
        self.assertEqual(set(ScreenTimeDaily.objects.values_list('pk', flat=True)), {keep_today.pk, one_day.pk})
        # --days 0 is clamped to 1: today and yesterday stay (cutoff is strict).
        self.run_command('purge_screen_time', '--days', '0')
        self.assertEqual(set(ScreenTimeDaily.objects.values_list('pk', flat=True)), {keep_today.pk, one_day.pk})
        self.assertFalse(ScreenTimeDaily.objects.filter(pk=older.pk).exists())


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class SeedDemoCommandTests(NoNetworkMixin, TestCase):
    @override_settings(DEMO_ACCOUNTS_ENABLED=False)
    def test_disabled_environment_skips(self):
        self.assertIn('skipping seed_demo', self.run_command('seed_demo'))
        self.assertFalse(User.objects.exists())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True)
    def test_seed_creates_demo_data_and_is_idempotent(self):
        self.run_command('seed_demo')
        counts = {
            'users': User.objects.count(),
            'students': StudentProfile.objects.count(),
            'tasks': Task.objects.count(),
            'applications': Application.objects.count(),
        }
        self.assertTrue(User.objects.filter(role=User.Role.COUNSELOR).exists())
        self.assertTrue(User.objects.filter(role=User.Role.STUDENT).exists())
        self.assertGreater(counts['students'], 1)
        self.assertGreater(counts['tasks'], 0)
        # Every demo student has a profile (no profile-less student accounts).
        self.assertFalse(User.objects.filter(role=User.Role.STUDENT, student_profile__isnull=True).exists())
        self.run_command('seed_demo')
        self.assertEqual({
            'users': User.objects.count(),
            'students': StudentProfile.objects.count(),
            'tasks': Task.objects.count(),
            'applications': Application.objects.count(),
        }, counts)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class ResetDemoCommandTests(NoNetworkMixin, TestCase):
    def tearDown(self):
        # flush + post_migrate may recreate content types/permissions with new
        # ids inside this (rolled back) transaction; drop the stale cache.
        ContentType.objects.clear_cache()
        super().tearDown()

    @override_settings(DEMO_ACCOUNTS_ENABLED=False)
    def test_refuses_when_demo_accounts_are_disabled(self):
        User.objects.create_user(username='keep-me', password=None)
        with self.assertRaisesMessage(CommandError, 'Demo accounts are disabled'):
            self.run_command('reset_demo')
        self.assertTrue(User.objects.filter(username='keep-me').exists())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True)
    def test_flushes_then_reseeds(self):
        User.objects.create_user(username='stray-user', password=None)
        if connection.vendor == 'postgresql':
            # TestCase wraps us in a transaction with deferred FK checks pending;
            # PostgreSQL refuses to TRUNCATE (flush) until they have fired.
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        # reset_demo calls seed_demo without forwarding stdout; keep the test output clean.
        with mock.patch('sys.stdout', new_callable=StringIO):
            output = self.run_command('reset_demo')
        self.assertIn('Demo reset done.', output)
        self.assertFalse(User.objects.filter(username='stray-user').exists())
        self.assertTrue(User.objects.filter(role=User.Role.COUNSELOR).exists())
        self.assertTrue(Permission.objects.exists())


class MigrateLockedCommandTests(NoNetworkMixin, TestCase):
    TARGET = 'apps.users.management.commands.migrate_locked.call_command'

    def held_advisory_locks(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
            )
            return cursor.fetchone()[0]

    def test_delegates_to_migrate_with_options(self):
        with mock.patch(self.TARGET) as migrate:
            self.run_command('migrate_locked', '--noinput')
        migrate.assert_called_once()
        args, kwargs = migrate.call_args
        self.assertEqual(args, ('migrate',))
        self.assertEqual(kwargs['database'], 'default')
        self.assertFalse(kwargs['interactive'])
        if connection.vendor == 'postgresql':
            self.assertEqual(self.held_advisory_locks(), 0)

    def test_lock_is_released_when_migrate_fails(self):
        with mock.patch(self.TARGET, side_effect=RuntimeError('boom')):
            with self.assertRaisesMessage(RuntimeError, 'boom'):
                self.run_command('migrate_locked', '--noinput')
        if connection.vendor == 'postgresql':
            self.assertEqual(self.held_advisory_locks(), 0)

    def test_real_run_with_nothing_to_apply(self):
        output = self.run_command('migrate_locked', '--noinput', verbosity=1)
        self.assertIn('No migrations to apply', output)
