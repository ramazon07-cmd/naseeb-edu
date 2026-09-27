"""The student's notification bell: list, unread summary and read marking."""
import importlib
from datetime import timedelta
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import (
    Booking, ChannelMembership, ChannelMessage, Document, MessageChannel, Notification, StudentMessage, Task,
)
from apps.admissions.test_audit_base import AuditBaseMixin


class NotificationBellTests(AuditBaseMixin, APITestCase):
    def notify(self, student=None, **extra):
        return Notification.objects.create(
            student=student or self.student, title=extra.pop('title', 'Notice'), message='Body', **extra,
        )

    def counted(self, method, url):
        with CaptureQueriesContext(connection) as context:
            response = getattr(self.client, method)(url)
        return len(context.captured_queries), response

    def test_student_lists_only_their_own_notifications_newest_first(self):
        old = self.notify(title='Old')
        Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        new = self.notify(title='New')
        self.notify(self.student_b, title='Foreign')
        self.client.force_authenticate(self.student_user)
        rows = self.results(self.client.get('/api/notifications/'))
        self.assertEqual([row['id'] for row in rows], [new.pk, old.pk])

    def test_cursor_pages_are_bounded_and_cost_the_same(self):
        self.client.force_authenticate(self.student_user)
        self.notify()
        first_cost, _ = self.counted('get', '/api/notifications/?cursor=&page_size=2')
        for _ in range(6):
            self.notify()
        cost, first = self.counted('get', '/api/notifications/?cursor=&page_size=2')
        self.assertEqual(cost, first_cost)
        self.assertEqual(len(first.data['results']), 2)
        self.assertTrue(first.data['has_more'])
        seen = [row['id'] for row in first.data['results']]
        next_url = first.data['next']
        while next_url:
            page = self.client.get(next_url).data
            seen += [row['id'] for row in page['results']]
            next_url = page['next']
        expected = list(Notification.objects.filter(student=self.student).order_by('-created_at', '-id')
                        .values_list('id', flat=True))
        self.assertEqual(seen, expected)

    def test_summary_counts_unread_notices_counselor_messages_and_chats(self):
        self.notify()
        self.notify(is_read=True)
        self.notify(self.student_b)
        StudentMessage.objects.create(student=self.student, sender=self.counselor, recipient=self.student_user,
                                      body='Hello')
        StudentMessage.objects.create(student=self.student, sender=self.counselor, recipient=self.student_user,
                                      body='Read', is_read=True)
        StudentMessage.objects.create(student=self.student, sender=self.student_user, recipient=self.counselor,
                                      body='Mine')
        channel = MessageChannel.objects.create(kind=MessageChannel.Kind.DIRECT, school=self.school_a)
        ChannelMembership.objects.create(channel=channel, user=self.student_user)
        ChannelMembership.objects.create(channel=channel, user=self.counselor)
        ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='One')
        ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='Two')
        ChannelMessage.objects.create(channel=channel, sender=self.student_user, body='Own')
        self.client.force_authenticate(self.student_user)
        cost, response = self.counted('get', '/api/notifications/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            (response.data['unread'], response.data['counselor_messages_unread'], response.data['chats_unread']),
            (1, 1, 2),
        )
        for _ in range(5):
            self.notify()
            ChannelMessage.objects.create(channel=channel, sender=self.counselor, body='More')
        self.assertEqual(self.counted('get', '/api/notifications/summary/')[0], cost)
        self.assertLessEqual(cost, 4)

    def test_summary_is_capped(self):
        Notification.objects.bulk_create([
            Notification(student=self.student, title='Bulk', message='Body') for _ in range(105)
        ])
        self.client.force_authenticate(self.student_user)
        data = self.client.get('/api/notifications/summary/').data
        self.assertEqual((data['unread'], data['limit']), (100, 100))

    def test_counselor_summary_never_counts_student_notices(self):
        self.notify()
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['unread'], 0)

    def test_mark_one_read_is_idempotent(self):
        notice = self.notify()
        self.client.force_authenticate(self.student_user)
        response = self.client.post(f'/api/notifications/{notice.pk}/read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_read'])
        notice.refresh_from_db()
        stamp = notice.updated_at
        with CaptureQueriesContext(connection) as context:
            again = self.client.post(f'/api/notifications/{notice.pk}/read/')
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertFalse(any(query['sql'].startswith('UPDATE') for query in context.captured_queries))
        notice.refresh_from_db()
        self.assertEqual(notice.updated_at, stamp)

    def test_mark_all_read_touches_only_the_callers_notices(self):
        mine = [self.notify(), self.notify()]
        foreign = self.notify(self.student_b)
        self.client.force_authenticate(self.student_user)
        response = self.client.post('/api/notifications/read-all/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['updated'], 2)
        self.assertEqual(Notification.objects.filter(pk__in=[n.pk for n in mine], is_read=True).count(), 2)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)
        self.assertEqual(self.client.post('/api/notifications/read-all/').data['updated'], 0)

    def test_student_cannot_read_or_mark_another_students_notice(self):
        foreign = self.notify(self.student_b)
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get(f'/api/notifications/{foreign.pk}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(f'/api/notifications/{foreign.pk}/read/').status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(f'/api/notifications/{foreign.pk}/', {'is_read': True}, format='json')
                         .status_code, status.HTTP_403_FORBIDDEN)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)

    def test_counselor_mark_all_does_not_clear_student_alerts(self):
        notice = self.notify()
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post('/api/notifications/read-all/').data['updated'], 0)
        notice.refresh_from_db()
        self.assertFalse(notice.is_read)

    def test_link_fields_are_server_owned(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/notifications/', {
            'student': self.student.pk, 'title': 'Hi', 'message': 'Body', 'kind': 'essay', 'target_id': 99,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual((response.data['kind'], response.data['target_id']), ('general', None))


class NotificationKindTests(AuditBaseMixin, APITestCase):
    def run_job(self):
        call_command('generate_notifications', stdout=StringIO())
        return {n.title: n for n in Notification.objects.filter(student=self.student)}

    def test_generated_alerts_say_what_they_are_about(self):
        today = timezone.localdate()
        Task.objects.create(student=self.student, title='Late', status=Task.Status.TODO,
                            due_date=today - timedelta(days=2))
        Document.objects.create(student=self.student, title='Passport', status=Document.Status.REQUIRED)
        notices = self.run_job()
        self.assertEqual(notices['Late tasks require attention'].kind, Notification.Kind.TASK)
        self.assertEqual(notices['Required documents are missing'].kind, Notification.Kind.DOCUMENT)

    def test_a_raised_again_alert_returns_to_the_top(self):
        task = Task.objects.create(student=self.student, title='Late', status=Task.Status.TODO,
                                   due_date=timezone.localdate() - timedelta(days=2))
        notice = self.run_job()['Late tasks require attention']
        Notification.objects.filter(pk=notice.pk).update(
            is_read=True, created_at=timezone.now() - timedelta(days=5),
        )
        still_unread = self.run_job()['Late tasks require attention']
        self.assertGreater(still_unread.created_at, timezone.now() - timedelta(minutes=1))
        # An alert that stays unread keeps its place.
        stamp = still_unread.created_at
        self.assertEqual(self.run_job()['Late tasks require attention'].created_at, stamp)

    def test_meeting_updates_are_meeting_notices(self):
        booking = Booking.objects.create(student=self.student, participant=self.counselor, topic='Plan',
                                         starts_at=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/bookings/{booking.pk}/approve/').status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.get(student=self.student).kind, Notification.Kind.MEETING)

    def test_existing_notices_are_backfilled_from_their_titles(self):
        titles = {
            'Late tasks require attention': 'task', 'Required documents are missing': 'document',
            'University deadline approaching': 'deadline', 'Essay shared with counselor': 'essay',
            'Meeting approved': 'meeting', 'Something else': 'general',
        }
        for title in titles:
            Notification.objects.create(student=self.student, title=title, message='Body')
        migration = importlib.import_module('apps.admissions.migrations.0057_snotif_notification_kind')
        migration.backfill_kinds(django_apps, None)
        self.assertEqual(
            dict(Notification.objects.filter(student=self.student).values_list('title', 'kind')), titles,
        )


class CounselorInboxTests(AuditBaseMixin, APITestCase):
    """The legacy counselor -> student messages the student portal shows as a thread."""

    def message(self, sender, recipient, student=None, **extra):
        return StudentMessage.objects.create(
            student=student or self.student, sender=sender, recipient=recipient, body='Body', **extra,
        )

    def test_student_pages_their_thread_newest_first(self):
        first = self.message(self.counselor, self.student_user)
        reply = self.message(self.student_user, self.counselor)
        self.message(self.counselor_b, self.student_b_user, student=self.student_b)
        self.client.force_authenticate(self.student_user)
        page = self.client.get('/api/student-messages/?cursor=&page_size=1').data
        self.assertEqual([row['id'] for row in page['results']], [reply.pk])
        older = self.client.get(page['next']).data
        self.assertEqual([row['id'] for row in older['results']], [first.pk])
        self.assertFalse(older['has_more'])

    def test_read_all_marks_only_messages_sent_to_the_student(self):
        received = self.message(self.counselor, self.student_user)
        sent = self.message(self.student_user, self.counselor)
        foreign = self.message(self.counselor_b, self.student_b_user, student=self.student_b)
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['counselor_messages_unread'], 1)
        response = self.client.post('/api/student-messages/read-all/')
        self.assertEqual((response.status_code, response.data['updated']), (status.HTTP_200_OK, 1))
        for row, expected in ((received, True), (sent, False), (foreign, False)):
            row.refresh_from_db()
            self.assertEqual(row.is_read, expected)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['counselor_messages_unread'], 0)
        self.assertEqual(self.client.post('/api/student-messages/read-all/').data['updated'], 0)

    def test_student_cannot_mark_another_students_message(self):
        foreign = self.message(self.counselor_b, self.student_b_user, student=self.student_b)
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.post(f'/api/student-messages/{foreign.pk}/read/').status_code,
                         status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)

    def test_read_all_leaves_staff_inboxes_alone(self):
        to_counselor = self.message(self.student_user, self.counselor)
        to_student = self.message(self.counselor, self.student_user)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post('/api/student-messages/read-all/').data['updated'], 0)
        to_counselor.refresh_from_db()
        to_student.refresh_from_db()
        self.assertEqual((to_counselor.is_read, to_student.is_read), (False, False))
