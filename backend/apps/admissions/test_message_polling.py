"""Message polling revalidation: ETag / If-None-Match on the channel message list."""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions.models import ChannelMembership, ChannelMessage, MessageChannel, MessageReport

from .test_audit_base import AuditBaseMixin


class MessagePollingETagTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.room = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Room', school=self.school_a, is_public=True,
        )
        ChannelMembership.objects.create(channel=self.room, user=self.counselor, role=ChannelMembership.Role.OWNER)
        ChannelMembership.objects.create(channel=self.room, user=self.student_user)
        self.private = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='Staff', school=self.school_a)
        ChannelMembership.objects.create(channel=self.private, user=self.counselor, role=ChannelMembership.Role.OWNER)
        self.first = ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='Welcome')
        ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='Hello')
        ChannelMessage.objects.create(channel=self.private, sender=self.counselor, body='Staff only')
        self.url = f'/api/channel-messages/?channel={self.room.id}&page_size=50'
        self.client.force_authenticate(self.student_user)

    def poll(self, etag=None, url=None):
        headers = {'HTTP_IF_NONE_MATCH': etag} if etag else {}
        return self.client.get(url or self.url, **headers)

    def assert_changed(self, etag):
        response = self.poll(etag)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response['ETag'], etag)
        return response['ETag']

    def test_unchanged_poll_is_304_without_a_body(self):
        first = self.poll()
        self.assertEqual(first.status_code, 200)
        etag = first['ETag']
        self.assertTrue(etag.startswith('W/"'))
        self.assertEqual(len(self.results(first)), 2)
        again = self.poll(etag)
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b'')
        self.assertEqual(again['ETag'], etag)
        # Weak comparison and lists of tags, as proxies may rewrite them.
        self.assertEqual(self.poll(etag.removeprefix('W/')).status_code, 304)
        self.assertEqual(self.poll(f'W/"stale", {etag}').status_code, 304)

    def test_304_costs_fewer_queries_than_a_full_page(self):
        etag = self.poll()['ETag']
        with CaptureQueriesContext(connection) as full:
            self.poll()
        with CaptureQueriesContext(connection) as revalidated:
            self.assertEqual(self.poll(etag).status_code, 304)
        self.assertLess(len(revalidated.captured_queries), len(full.captured_queries))
        # Changed since: one extra narrow query on top of the normal page.
        ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='New')
        with CaptureQueriesContext(connection) as changed:
            self.assertEqual(self.poll(etag).status_code, 200)
        self.assertEqual(len(changed.captured_queries), len(full.captured_queries) + 1)

    def test_every_visible_change_gives_a_new_etag(self):
        etag = self.poll()['ETag']
        mine = ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='Draft')
        etag = self.assert_changed(etag)  # new message
        self.assertEqual(self.client.patch(f'/api/channel-messages/{mine.id}/?channel={self.room.id}',
                                           {'body': 'Edited'}, format='json').status_code, 200)
        etag = self.assert_changed(etag)  # edit
        ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='Reply', parent=self.first)
        etag = self.assert_changed(etag)  # reply (new row and the parent's reply count)
        MessageReport.objects.create(message=self.first, reporter=self.student_user, reason='spam')
        etag = self.assert_changed(etag)  # the caller's own report
        self.assertEqual(self.client.delete(f'/api/channel-messages/{mine.id}/?channel={self.room.id}').status_code, 204)
        etag = self.assert_changed(etag)  # soft delete
        self.assertEqual(self.poll(etag).status_code, 304)

    def test_parent_edit_outside_the_page_changes_the_reply_preview(self):
        old = ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='Old question')
        ChannelMessage.objects.create(channel=self.room, sender=self.student_user, body='Answer', parent=old)
        url = f'/api/channel-messages/?channel={self.room.id}&page_size=1'
        etag = self.poll(url=url)['ETag']
        ChannelMessage.objects.filter(pk=old.pk).update(body='Old question, edited', updated_at=old.updated_at.replace(year=2030))
        response = self.poll(etag, url=url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.results(response)[0]['parent_preview']['body'], 'Old question, edited')

    def test_etags_are_per_user_and_per_page(self):
        student_etag = self.poll()['ETag']
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.poll(student_etag).status_code, 200, 'another user never revalidates my copy')
        self.client.force_authenticate(self.student_user)
        smaller = f'/api/channel-messages/?channel={self.room.id}&page_size=1'
        self.assertEqual(self.poll(student_etag, url=smaller).status_code, 200)

    def test_revalidation_keeps_channel_scoping(self):
        # The counselor can read the private staff channel; the student can't.
        private_url = f'/api/channel-messages/?channel={self.private.id}&page_size=50'
        self.client.force_authenticate(self.counselor)
        counselor_etag = self.poll(url=private_url)['ETag']
        self.client.force_authenticate(self.student_user)
        response = self.poll(counselor_etag, url=private_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.results(response), [])
        # The student's own tag for the (empty, inaccessible) page reveals nothing either.
        outsider_etag = response['ETag']
        ChannelMessage.objects.create(channel=self.private, sender=self.counselor, body='More staff talk')
        self.assertEqual(self.poll(outsider_etag, url=private_url).status_code, 304)

    def test_malformed_page_skips_revalidation(self):
        etag = self.poll()['ETag']
        response = self.poll(etag, url=f'{self.url}&page=abc')
        self.assertNotEqual(response.status_code, 304)


class OlderMessagesTests(AuditBaseMixin, APITestCase):
    """?before=<id> reaches every message of a long conversation, page by page."""

    def setUp(self):
        super().setUp()
        self.room = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='Room', school=self.school_a)
        ChannelMembership.objects.create(channel=self.room, user=self.counselor, role=ChannelMembership.Role.OWNER)
        ChannelMembership.objects.create(channel=self.room, user=self.student_user)
        self.other = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='Other', school=self.school_a)
        ChannelMembership.objects.create(channel=self.other, user=self.counselor, role=ChannelMembership.Role.OWNER)
        self.foreign = ChannelMessage.objects.create(channel=self.other, sender=self.counselor, body='Elsewhere')
        # Equal timestamps on purpose: the id breaks ties, so no row is skipped or repeated.
        stamp = ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='0').created_at
        ChannelMessage.objects.bulk_create([
            ChannelMessage(channel=self.room, sender=self.counselor, body=str(index), created_at=stamp)
            for index in range(1, 12)
        ])
        self.client.force_authenticate(self.student_user)

    def page(self, before=None, size=5):
        url = f'/api/channel-messages/?channel={self.room.id}&page_size={size}'
        return self.client.get(f'{url}&before={before}' if before else url)

    def test_pages_walk_back_to_the_first_message(self):
        response = self.page()
        seen = [row['id'] for row in response.data['results']]
        while response.data['next']:
            response = self.page(before=seen[-1])
            self.assertEqual(response.status_code, 200)
            seen += [row['id'] for row in response.data['results']]
        expected = list(ChannelMessage.objects.filter(channel=self.room).order_by('-created_at', '-id')
                        .values_list('id', flat=True))
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 12)

    def test_older_pages_are_stable_while_new_messages_arrive(self):
        first = [row['id'] for row in self.page().data['results']]
        ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='New')
        older = [row['id'] for row in self.page(before=first[-1]).data['results']]
        self.assertFalse(set(first) & set(older))
        self.assertTrue(all(pk < first[-1] for pk in older))

    def test_an_older_page_costs_the_same_as_the_first(self):
        oldest = self.page().data['results'][-1]['id']
        with CaptureQueriesContext(connection) as small:
            self.page(before=oldest)
        ChannelMessage.objects.bulk_create([
            ChannelMessage(channel=self.room, sender=self.counselor, body='bulk') for _ in range(30)
        ])
        with CaptureQueriesContext(connection) as large:
            self.page(before=oldest)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))

    def test_anchor_must_belong_to_the_conversation(self):
        self.assertEqual(self.page(before=self.foreign.id).status_code, 400)
        self.assertEqual(self.page(before=999999).status_code, 400)
        self.assertEqual(self.page(before='abc').status_code, 400)

    def test_polling_an_older_page_revalidates_it_separately(self):
        newest = self.page()
        oldest = newest.data['results'][-1]['id']
        older = self.page(before=oldest)
        self.assertNotEqual(newest['ETag'], older['ETag'])
        url = f'/api/channel-messages/?channel={self.room.id}&page_size=5&before={oldest}'
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=older['ETag']).status_code, 304)
