"""Chat read receipts: ``peer_last_read_at`` on channels and a ``mark-read`` that only moves forward.

The frontend shows two ticks on the requester's own messages created at or
before ``peer_last_read_at``. Only members get it; everyone else gets null.
"""
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import ChannelMembership, ChannelMessage, MessageChannel
from .base import RoleIsolationBase


class ReadReceiptTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.direct = MessageChannel.objects.create(
            kind=MessageChannel.Kind.DIRECT, school=self.school_a, direct_key='receipts', created_by=self.counselor,
        )
        self.counselor_seat = ChannelMembership.objects.create(channel=self.direct, user=self.counselor)
        self.student_seat = ChannelMembership.objects.create(channel=self.direct, user=self.student_a_user)

    def channel(self, user, channel):
        self.client.force_authenticate(user)
        listed = next(row for row in self.results(self.client.get('/api/message-channels/')) if row['id'] == channel.id)
        detail = self.client.get(f'/api/message-channels/{channel.id}/').data
        self.assertEqual(listed['peer_last_read_at'], detail['peer_last_read_at'])
        return listed['peer_last_read_at']

    def send(self, user, channel, body='Hello'):
        self.client.force_authenticate(user)
        response = self.client.post('/api/channel-messages/', {'channel': channel.id, 'body': body}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return parse_datetime(response.data['created_at'])

    def mark_read(self, user, channel):
        self.client.force_authenticate(user)
        response = self.client.post(f'/api/message-channels/{channel.id}/mark-read/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_direct_chat_shows_when_the_recipient_read(self):
        sent = self.send(self.counselor, self.direct)
        self.assertIsNone(self.channel(self.counselor, self.direct))  # sent: one tick
        self.mark_read(self.student_a_user, self.direct)
        self.assertGreaterEqual(parse_datetime(self.channel(self.counselor, self.direct)), sent)  # read: two ticks
        # Writing counts as reading for the writer, so the student sees the counselor's read time too.
        self.assertEqual(parse_datetime(self.channel(self.student_a_user, self.direct)), sent)

    def test_mark_read_never_moves_backwards(self):
        later = timezone.now() + timedelta(hours=1)
        ChannelMembership.objects.filter(pk=self.student_seat.pk).update(last_read_at=later)
        self.mark_read(self.student_a_user, self.direct)
        self.student_seat.refresh_from_db()
        self.assertEqual(self.student_seat.last_read_at, later)
        # Posting does not pull it back either.
        self.send(self.student_a_user, self.direct)
        self.student_seat.refresh_from_db()
        self.assertEqual(self.student_seat.last_read_at, later)

    def test_a_group_counts_as_read_when_any_other_member_read(self):
        group = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='G', school=self.school_a)
        for user in (self.counselor, self.student_a_user, self.teacher):
            ChannelMembership.objects.create(channel=group, user=user)
        sent = self.send(self.counselor, group)
        self.assertIsNone(self.channel(self.counselor, group))
        self.mark_read(self.teacher, group)
        self.assertGreaterEqual(parse_datetime(self.channel(self.counselor, group)), sent)

    def test_non_members_never_get_a_receipt(self):
        community = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Everyone', school=self.school_a, is_public=True,
        )
        ChannelMembership.objects.create(channel=community, user=self.counselor, last_read_at=timezone.now())
        ChannelMembership.objects.create(channel=community, user=self.teacher, last_read_at=timezone.now())
        # The organization sees the public community without being in it.
        self.client.force_authenticate(self.organization)
        detail = self.client.get(f'/api/message-channels/{community.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.data['peer_last_read_at'])
        listed = [row for row in self.results(self.client.get('/api/message-channels/')) if row['id'] == community.id]
        self.assertEqual([row['peer_last_read_at'] for row in listed], [None])
        self.assertEqual(self.client.post(f'/api/message-channels/{community.id}/mark-read/').status_code, 403)
        # A private chat stays invisible to outsiders, receipt included.
        self.mark_read(self.student_a_user, self.direct)
        for outsider in (self.student_b_user, self.counselor_b, self.teacher):
            self.client.force_authenticate(outsider)
            with self.subTest(user=outsider.username):
                self.assertEqual(self.client.get(f'/api/message-channels/{self.direct.id}/').status_code, 404)
                rows = self.results(self.client.get('/api/message-channels/'))
                self.assertNotIn(self.direct.id, [row['id'] for row in rows])
                self.assertEqual(self.client.post(f'/api/message-channels/{self.direct.id}/mark-read/').status_code, 404)
        self.counselor_seat.refresh_from_db()
        self.assertIsNone(self.counselor_seat.last_read_at)

    def test_single_channel_responses_carry_the_receipt_too(self):
        ChannelMessage.objects.create(channel=self.direct, sender=self.counselor, body='Hi')
        self.mark_read(self.student_a_user, self.direct)
        self.direct.direct_key = f'{min(self.counselor.id, self.student_a_user.id)}:{max(self.counselor.id, self.student_a_user.id)}'
        self.direct.save(update_fields=['direct_key'])
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/message-channels/direct/', {'user': self.student_a_user.id}, format='json')
        self.assertEqual((response.status_code, response.data['id']), (200, self.direct.id))
        self.assertIsNotNone(response.data['peer_last_read_at'])
