"""Messaging: channel overview counts and message-report moderation.

The resolve path takes a row lock with
select_for_update(of=('self',)); run this module on PostgreSQL too, where the
lock is real (SQLite ignores it).
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import ChannelMembership, ChannelMessage, MessageChannel, MessageReport
from apps.users.models import User

from .test_audit_base import AuditBaseMixin

Kind = MessageChannel.Kind
Role = ChannelMembership.Role
OVERVIEW = '/api/message-channels/overview/'
REPORTS = '/api/message-reports/'


def channel(kind, name, school, members=(), *, public=None, **extra):
    created = MessageChannel.objects.create(
        kind=kind, name=name, school=school,
        is_public=kind in {Kind.COMMUNITY, Kind.DISCUSSION} if public is None else public, **extra,
    )
    for member in members:
        if isinstance(member, tuple):
            ChannelMembership.objects.create(channel=created, user=member[0], role=member[1])
        else:
            ChannelMembership.objects.create(channel=created, user=member)
    return created


class ChannelOverviewTests(AuditBaseMixin, APITestCase):
    """The membership join (and, for counselors, the school->students join)
    must not multiply public channels in channel_counts."""

    def setUp(self):
        super().setUp()
        # Extra assigned students in school A: each one multiplies the
        # counselor's ``school__students__assigned_counselor`` join.
        self.classmates = []
        for index in range(3):
            user = self.make_user(f'ov-classmate-{index}', User.Role.STUDENT, self.school_a)
            self.make_profile(user, self.school_a, self.counselor)
            self.classmates.append(user)
        everyone_a = [self.counselor, self.teacher, self.organization, self.student_user, *self.classmates]
        self.community = channel(Kind.COMMUNITY, 'Busy community', self.school_a, everyone_a)
        self.discussion = channel(Kind.DISCUSSION, 'Open question', self.school_a, everyone_a[:5])
        self.global_community = channel(
            Kind.COMMUNITY, 'Global', None, [self.counselor_b, self.student_b_user], is_global=True,
        )
        channel(Kind.COMMUNITY, 'Other school', self.school_b, [self.counselor_b, self.student_b_user])
        self.group = channel(Kind.GROUP, 'Study group', self.school_a, [self.counselor, self.student_user, self.teacher])
        channel(Kind.GROUP, 'Private staff room', self.school_a, [self.teacher, self.organization])
        first, second = sorted([self.counselor.id, self.student_user.id])
        self.direct = channel(
            Kind.DIRECT, '', None, [self.counselor, self.student_user], direct_key=f'{first}:{second}',
        )

    def overview(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(OVERVIEW)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_student_counts_each_visible_channel_once(self):
        data = self.overview(self.student_user)
        self.assertEqual(data['channel_counts'], {'direct': 1, 'group': 1, 'community': 2, 'discussion': 1})
        self.assertFalse(data['can_moderate'])
        self.assertEqual(data['pending_reports'], 0)

    def test_counselor_counts_are_not_multiplied_by_assigned_students(self):
        data = self.overview(self.counselor)
        self.assertEqual(data['channel_counts'], {'direct': 1, 'group': 1, 'community': 2, 'discussion': 1})
        self.assertTrue(data['can_moderate'])

    def test_cross_school_assignment_does_not_open_that_schools_public_channels(self):
        # A counselor whose own school is B but who has a student in school A.
        roaming = self.make_user('ov-roaming', User.Role.COUNSELOR, self.school_b)
        self.student.assigned_counselor = roaming
        self.student.save(update_fields=['assigned_counselor'])
        data = self.overview(roaming)
        # Only school B's 'Other school' and the global community.
        self.assertEqual(data['channel_counts']['community'], 2)
        self.assertEqual(data['channel_counts']['discussion'], 0)
        self.assertEqual(data['channel_counts']['group'], 0)

    def test_admin_counts_every_channel_once(self):
        data = self.overview(self.admin)
        self.assertEqual(data['channel_counts'], {'direct': 1, 'group': 2, 'community': 3, 'discussion': 1})

    def test_unread_total_counts_other_peoples_live_messages_since_last_read(self):
        ChannelMessage.objects.create(channel=self.community, sender=self.counselor, body='one')
        ChannelMessage.objects.create(channel=self.community, sender=self.teacher, body='two')
        ChannelMessage.objects.create(channel=self.community, sender=self.student_user, body='mine')
        ChannelMessage.objects.create(
            channel=self.community, sender=self.teacher, body='', deleted_at=timezone.now(),
        )
        ChannelMessage.objects.create(channel=self.group, sender=self.counselor, body='three')
        # Public channel the student is not a member of: not counted as unread.
        ChannelMessage.objects.create(channel=self.global_community, sender=self.counselor_b, body='x')
        self.assertEqual(self.overview(self.student_user)['unread_total'], 3)

        ChannelMembership.objects.filter(channel=self.community, user=self.student_user).update(
            last_read_at=timezone.now() + timedelta(seconds=1),
        )
        self.assertEqual(self.overview(self.student_user)['unread_total'], 1)

    def test_pending_reports_only_counts_moderated_open_reports(self):
        ChannelMembership.objects.filter(channel=self.community, user=self.counselor).update(role=Role.OWNER)
        message = ChannelMessage.objects.create(channel=self.community, sender=self.student_user, body='bad')
        other = ChannelMessage.objects.create(channel=self.community, sender=self.student_user, body='bad 2')
        closed = ChannelMessage.objects.create(channel=self.community, sender=self.student_user, body='old')
        MessageReport.objects.create(message=message, reporter=self.classmates[0], reason='spam')
        MessageReport.objects.create(message=message, reporter=self.classmates[1], reason='spam', status='reviewing')
        MessageReport.objects.create(message=other, reporter=self.classmates[0], reason='spam')
        MessageReport.objects.create(message=closed, reporter=self.classmates[0], reason='spam', status='dismissed')
        # Report in a channel the counselor does not moderate.
        unmoderated = ChannelMessage.objects.create(channel=self.group, sender=self.student_user, body='g')
        MessageReport.objects.create(message=unmoderated, reporter=self.teacher, reason='spam')
        self.assertEqual(self.overview(self.counselor)['pending_reports'], 3)


class MessageReportModerationTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.classmate = self.make_user('mod-classmate', User.Role.STUDENT, self.school_a)
        self.make_profile(self.classmate, self.school_a, self.counselor)
        self.room = channel(Kind.COMMUNITY, 'Moderated room', self.school_a, [
            (self.counselor, Role.OWNER), (self.teacher, Role.MODERATOR), self.organization,
            self.student_user, self.classmate,
        ])
        self.message = ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='rude')
        self.report = self.file_report(self.classmate, self.message)

    def file_report(self, reporter, message, reason='harassment'):
        self.client.force_authenticate(reporter)
        response = self.client.post(
            f'/api/channel-messages/{message.id}/report/', {'reason': reason, 'details': ' why '}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], MessageReport.Status.PENDING)
        return MessageReport.objects.get(pk=response.data['id'])

    def act(self, user, verb, report=None, **data):
        self.client.force_authenticate(user)
        return self.client.post(f'{REPORTS}{(report or self.report).id}/{verb}/', data, format='json')

    # --- filing ---------------------------------------------------------

    def test_report_filing_rules(self):
        self.assertEqual(self.report.details, 'why')
        url = f'/api/channel-messages/{self.message.id}/report/'
        self.client.force_authenticate(self.classmate)
        self.assertEqual(self.client.post(url, {'reason': 'spam'}, format='json').status_code, 400)  # duplicate
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.post(url, {'reason': 'spam'}, format='json').status_code, 400)  # own message
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(url, {'reason': 'nope'}, format='json').status_code, 400)
        self.assertEqual(
            self.client.post(url, {'reason': 'spam', 'details': 'x' * 2001}, format='json').status_code, 400,
        )
        outsider = self.make_user('mod-outsider', User.Role.STUDENT, self.school_a)
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post(url, {'reason': 'spam'}, format='json').status_code, 403)
        self.assertEqual(MessageReport.objects.count(), 1)

    # --- access ---------------------------------------------------------

    def test_list_access(self):
        for user in (self.counselor, self.teacher, self.admin):
            self.client.force_authenticate(user)
            response = self.client.get(REPORTS)
            self.assertEqual(response.status_code, status.HTTP_200_OK, user.username)
            self.assertEqual([row['id'] for row in self.results(response)], [self.report.id], user.username)
        # Plain members, students and parents cannot moderate.
        for user in (self.organization, self.classmate, self.student_user, self.parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(REPORTS).status_code, status.HTTP_403_FORBIDDEN, user.username)
        # A moderator of some other channel cannot see or act on this report.
        channel(Kind.GROUP, 'Elsewhere', self.school_b, [(self.counselor_b, Role.OWNER)])
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.results(self.client.get(REPORTS)), [])
        self.assertEqual(self.act(self.counselor_b, 'dismiss').status_code, status.HTTP_404_NOT_FOUND)

    def test_list_filters(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(len(self.results(self.client.get(f'{REPORTS}?status=pending'))), 1)
        self.assertEqual(len(self.results(self.client.get(f'{REPORTS}?status=dismissed'))), 0)
        response = self.client.get(f'{REPORTS}?status=bogus')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.results(response), [])
        self.assertEqual(len(self.results(self.client.get(f'{REPORTS}?search=rude'))), 1)
        self.assertEqual(len(self.results(self.client.get(f'{REPORTS}?search=moderated'))), 1)
        self.assertEqual(len(self.results(self.client.get(f'{REPORTS}?search=zzz'))), 0)

    # --- review ---------------------------------------------------------

    def test_review_moves_pending_to_reviewing_once(self):
        response = self.act(self.teacher, 'review')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], MessageReport.Status.REVIEWING)
        self.report.refresh_from_db()
        self.assertEqual(self.report.reviewed_by, self.teacher)
        self.assertIsNotNone(self.report.reviewed_at)
        self.assertEqual(self.act(self.counselor, 'review').status_code, status.HTTP_400_BAD_REQUEST)

    # --- dismiss --------------------------------------------------------

    def test_dismiss_closes_report_without_touching_the_message(self):
        self.act(self.teacher, 'review')
        response = self.act(self.counselor, 'dismiss', moderator_note='  ok ' + 'n' * 3000)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MessageReport.Status.DISMISSED)
        self.assertEqual(self.report.action, MessageReport.Action.NONE)
        self.assertEqual(self.report.reviewed_by, self.counselor)
        self.assertEqual(len(self.report.moderator_note), 2000)
        self.assertTrue(self.report.moderator_note.startswith('ok '))
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, 'rude')
        self.assertIsNone(self.message.deleted_at)
        # Closed reports cannot be dismissed, reviewed or resolved again.
        self.assertEqual(self.act(self.counselor, 'dismiss').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.act(self.counselor, 'review').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.act(self.counselor, 'resolve').status_code, status.HTTP_400_BAD_REQUEST)

    # --- resolve --------------------------------------------------------

    def test_resolve_content_removed_deletes_message_and_closes_every_open_report(self):
        second = self.file_report(self.teacher, self.message, reason='unsafe')
        dismissed_elsewhere = ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='fine')
        untouched = self.file_report(self.classmate, dismissed_elsewhere)
        response = self.act(self.counselor, 'resolve', action='content_removed', moderator_note='removed')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], MessageReport.Status.RESOLVED)
        self.assertEqual(response.data['action'], MessageReport.Action.CONTENT_REMOVED)
        self.assertEqual(response.data['message_body'], 'Message deleted')
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, '')
        self.assertIsNotNone(self.message.deleted_at)
        for report in (self.report, second):
            report.refresh_from_db()
            self.assertEqual(report.status, MessageReport.Status.RESOLVED)
            self.assertEqual(report.action, MessageReport.Action.CONTENT_REMOVED)
            self.assertEqual(report.reviewed_by, self.counselor)
            self.assertEqual(report.moderator_note, 'removed')
        untouched.refresh_from_db()
        self.assertEqual(untouched.status, MessageReport.Status.PENDING)

    def test_resolve_mutes_author_and_never_shortens_an_existing_mute(self):
        before = timezone.now()
        response = self.act(self.teacher, 'resolve', action='muted_24h')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        membership = ChannelMembership.objects.get(channel=self.room, user=self.student_user)
        self.assertGreaterEqual(membership.muted_until, before + timedelta(hours=24))
        self.assertLess(membership.muted_until, before + timedelta(hours=25))
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, 'rude')

        # The muted author cannot post.
        self.client.force_authenticate(self.student_user)
        posted = self.client.post('/api/channel-messages/', {'channel': self.room.id, 'body': 'hi'}, format='json')
        self.assertEqual(posted.status_code, status.HTTP_400_BAD_REQUEST)

        # A 7-day mute extends it; a later 24h mute does not shorten it.
        second_message = ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='again')
        seven = self.file_report(self.classmate, second_message)
        self.assertEqual(self.act(self.counselor, 'resolve', seven, action='muted_7d').status_code, 200)
        membership.refresh_from_db()
        week_mute = membership.muted_until
        self.assertGreaterEqual(week_mute, before + timedelta(days=7))
        third_message = ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='third')
        short = self.file_report(self.classmate, third_message)
        self.assertEqual(self.act(self.counselor, 'resolve', short, action='muted_24h').status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.muted_until, week_mute)

    def test_resolve_mute_when_author_left_is_rejected_and_report_stays_open(self):
        ChannelMembership.objects.filter(channel=self.room, user=self.student_user).delete()
        response = self.act(self.counselor, 'resolve', action='muted_7d')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MessageReport.Status.PENDING)

    def test_resolve_rejects_unknown_action(self):
        response = self.act(self.counselor, 'resolve', action='ban_forever')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MessageReport.Status.PENDING)

    def test_resolve_with_no_action_closes_as_resolved(self):
        response = self.act(self.admin, 'resolve')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MessageReport.Status.RESOLVED)
        self.assertEqual(self.report.action, MessageReport.Action.NONE)
        self.assertEqual(self.report.reviewed_by, self.admin)

    def test_moderator_cannot_review_a_report_about_their_own_message(self):
        own = ChannelMessage.objects.create(channel=self.room, sender=self.teacher, body='teacher said')
        report = self.file_report(self.classmate, own)
        for verb in ('review', 'dismiss', 'resolve'):
            self.assertEqual(self.act(self.teacher, verb, report).status_code, status.HTTP_403_FORBIDDEN, verb)
        report.refresh_from_db()
        self.assertEqual(report.status, MessageReport.Status.PENDING)
        # Another moderator can.
        self.assertEqual(self.act(self.counselor, 'dismiss', report).status_code, status.HTTP_200_OK)
