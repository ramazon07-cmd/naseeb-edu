"""Cron commands: batched, idempotent, bounded queries, and one run at a time."""
from datetime import timedelta
from io import StringIO
from unittest import skipUnless

from django.core.management import call_command
from django.db import connection, connections
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.admissions.models import Document, Notification, ScreenTimeDaily, StudentProfile, Task
from apps.users.models import User
from core.jobs import delete_in_batches, job_lock_id

from .test_audit_base import AuditBaseMixin


def run(name, *args):
    output = StringIO()
    call_command(name, *args, stdout=output)
    return output.getvalue()


class DeleteInBatchesTests(AuditBaseMixin, TestCase):
    def test_deletes_everything_in_bounded_batches(self):
        for days in range(5):
            ScreenTimeDaily.objects.create(
                user=self.student_user, date=timezone.localdate() - timedelta(days=400 + days), page='home',
            )
        keep = ScreenTimeDaily.objects.create(user=self.student_user, date=timezone.localdate(), page='home')
        old = ScreenTimeDaily.objects.filter(date__lt=timezone.localdate() - timedelta(days=100))
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(delete_in_batches(old, batch_size=2), 5)
        selects = [q for q in queries.captured_queries if q['sql'].startswith('SELECT')]
        self.assertEqual(len(selects), 4)  # 2 + 2 + 1 rows, then an empty batch ends the loop
        self.assertEqual(list(ScreenTimeDaily.objects.values_list('pk', flat=True)), [keep.pk])

    def test_job_lock_ids_differ_per_job(self):
        names = ('flush_expired_tokens', 'purge_screen_time', 'generate_notifications')
        self.assertEqual(len({job_lock_id(name) for name in names}), 3)


class FlushExpiredTokensTests(AuditBaseMixin, TestCase):
    def token(self, jti, expires_in):
        now = timezone.now()
        return OutstandingToken.objects.create(
            user=self.student_user, jti=jti, token=f'token-{jti}', created_at=now, expires_at=now + expires_in,
        )

    def test_removes_expired_tokens_and_their_blacklist_rows(self):
        expired = [self.token(f'old-{i}', timedelta(days=-1)) for i in range(3)]
        BlacklistedToken.objects.create(token=expired[0])
        fresh = self.token('fresh', timedelta(days=5))
        BlacklistedToken.objects.create(token=fresh)
        output = run('flush_expired_tokens', '--batch-size', '2')
        self.assertIn('Deleted 3 expired refresh tokens.', output)
        self.assertEqual(list(OutstandingToken.objects.values_list('jti', flat=True)), ['fresh'])
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        self.assertIn('Deleted 0 expired refresh tokens.', run('flush_expired_tokens'))


class GenerateNotificationsScaleTests(AuditBaseMixin, TestCase):
    def add_student(self, index):
        user = self.make_user(f'job-student-{index}', User.Role.STUDENT, self.school_a)
        student = self.make_profile(user, self.school_a, self.counselor)
        Task.objects.create(student=student, title='Late', due_date=timezone.localdate() - timedelta(days=1))
        Document.objects.create(student=student, title='Passport', status=Document.Status.REQUIRED)
        return student

    def count_queries(self, *args):
        with CaptureQueriesContext(connection) as queries:
            run('generate_notifications', *args)
        return len(queries)

    def test_query_count_does_not_grow_with_students(self):
        self.add_student(0)
        one = self.count_queries()
        Notification.objects.all().delete()
        for index in range(1, 6):
            self.add_student(index)
        self.assertEqual(self.count_queries(), one)
        self.assertEqual(Notification.objects.count(), 12)

    def test_batches_cover_every_student_and_rerun_is_idempotent(self):
        students = [self.add_student(index) for index in range(5)]
        self.assertIn('Generated or refreshed 10 notifications.', run('generate_notifications', '--batch-size', '2'))
        Notification.objects.update(is_read=True)
        run('generate_notifications', '--batch-size', '2')
        self.assertEqual(Notification.objects.count(), 10)
        self.assertFalse(Notification.objects.filter(is_read=True).exists())
        self.assertEqual(
            set(Notification.objects.values_list('student_id', flat=True)), {student.pk for student in students},
        )

    def test_duplicate_rows_do_not_break_the_run(self):
        student = self.add_student(0)
        for _ in range(2):
            Notification.objects.create(student=student, title='Late tasks require attention', message='old', is_read=True)
        run('generate_notifications')
        rows = Notification.objects.filter(student=student, title='Late tasks require attention')
        self.assertEqual(set(rows.values_list('message', 'is_read')), {('1 task(s) are past their deadline.', False)})


@skipUnless(connection.vendor == 'postgresql', 'advisory locks need PostgreSQL')
class JobLockTests(AuditBaseMixin, TestCase):
    def test_a_second_run_skips_while_the_first_holds_the_lock(self):
        ScreenTimeDaily.objects.create(user=self.student_user, date=timezone.localdate() - timedelta(days=900), page='x')
        other = connections.create_connection('default')
        try:
            with other.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_lock(%s)', [job_lock_id('purge_screen_time')])
            self.assertIn('already running elsewhere; skipped', run('purge_screen_time'))
            self.assertEqual(ScreenTimeDaily.objects.count(), 1)
            with other.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [job_lock_id('purge_screen_time')])
            self.assertIn('Deleted 1 screen-time rows', run('purge_screen_time'))
        finally:
            other.close()
