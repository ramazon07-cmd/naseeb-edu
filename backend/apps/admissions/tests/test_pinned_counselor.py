"""The student's assigned counselor, pinned at the top of Messages (``counselor`` on /users/me/).

The row is there before anyone writes: ``direct_channel_id`` is null until the
chat exists, and opening it uses the existing direct action.
"""
from apps.users.models import User

from ..models import MessageChannel
from .base import RoleIsolationBase


class PinnedCounselorTests(RoleIsolationBase):
    def me(self, user):
        self.client.force_authenticate(user)
        response = self.client.get('/api/users/accounts/me/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_student_gets_their_counselor_before_any_message(self):
        counselor = self.me(self.student_a_user)['counselor']
        self.assertEqual(counselor['id'], self.counselor.id)
        self.assertEqual(counselor['full_name'], self.counselor.get_full_name() or self.counselor.username)
        self.assertIsNone(counselor['direct_channel_id'])

    def test_starting_the_chat_fills_in_its_channel(self):
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(opened.status_code, 201, opened.data)
        self.assertEqual(self.me(self.student_a_user)['counselor']['direct_channel_id'], opened.data['id'])
        # Opening it again returns the same chat, never a second one.
        again = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['id'], opened.data['id'])

    def test_student_without_a_counselor_gets_null(self):
        self.student_a.assigned_counselor = None
        self.student_a.save(update_fields=['assigned_counselor'])
        self.assertIsNone(self.me(self.student_a_user)['counselor'])

    def test_counselor_in_another_school_is_not_pinned(self):
        # Not a messaging contact of the student, so "start a conversation" could not work.
        self.student_a.assigned_counselor = self.counselor_b
        self.student_a.save(update_fields=['assigned_counselor'])
        self.assertIsNone(self.me(self.student_a_user)['counselor'])

    def test_inactive_counselor_is_not_pinned(self):
        User.objects.filter(pk=self.counselor.pk).update(is_active=False)
        self.assertIsNone(self.me(self.student_a_user)['counselor'])

    def test_staff_get_no_pinned_counselor(self):
        for user in (self.counselor, self.organization, self.teacher):
            self.assertIsNone(self.me(user)['counselor'])

    def test_saved_messages_is_never_taken_for_the_counselor_chat(self):
        MessageChannel.objects.create(
            kind=MessageChannel.Kind.DIRECT, direct_key=f'saved:{self.student_a_user.pk}',
            school=self.school_a, created_by=self.student_a_user,
        )
        self.assertIsNone(self.me(self.student_a_user)['counselor']['direct_channel_id'])

    def test_a_direct_chat_names_its_other_person_by_id(self):
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(opened.data['direct_peer_id'], self.counselor.id)
        listed = self.client.get('/api/message-channels/')
        rows = listed.data['results'] if isinstance(listed.data, dict) else listed.data
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id[opened.data['id']]['direct_peer_id'], self.counselor.id)
        saved = [row for row in rows if row['is_saved_messages']]
        self.assertTrue(all(row['direct_peer_id'] is None for row in saved))
        # The counselor sees the student on the same chat.
        self.client.force_authenticate(self.counselor)
        mine = self.client.get(f'/api/message-channels/{opened.data["id"]}/')
        self.assertEqual(mine.data['direct_peer_id'], self.student_a_user.id)
