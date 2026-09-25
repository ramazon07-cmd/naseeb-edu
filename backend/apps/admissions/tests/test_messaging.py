"""Role isolation: channels, direct messages, moderation."""
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import (
    ChannelMembership,
    ChannelMessage,
    MessageChannel,
    MessageReport,
    StudentProfile,
)
from .base import RoleIsolationBase


class MessagingRoleIsolationTests(RoleIsolationBase):
    def test_retired_community_feed_endpoints_are_unavailable(self):
        for account in (self.student_a_user, self.counselor, self.organization):
            self.client.force_authenticate(account)
            for path in ('/api/community-posts/', '/api/community-posts/1/like/'):
                with self.subTest(role=account.role, path=path):
                    self.assertEqual(self.client.get(path).status_code, status.HTTP_404_NOT_FOUND)
                    self.assertEqual(self.client.post(path, {}, format='json').status_code, status.HTTP_404_NOT_FOUND)

    def test_saved_messages_are_persistent_unique_and_private(self):
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/saved/', {}, format='json')
        self.assertEqual(opened.status_code, status.HTTP_201_CREATED)
        channel_id = opened.data['id']
        self.assertTrue(opened.data['is_saved_messages'])
        self.assertEqual(opened.data['members_count'], 1)
        reopened = self.client.post('/api/message-channels/saved/', {}, format='json')
        self.assertEqual(reopened.data['id'], channel_id)
        saved = self.client.post('/api/channel-messages/', {
            'channel': channel_id, 'body': 'Review my essay outline.',
        }, format='json')
        self.assertEqual(saved.status_code, status.HTTP_201_CREATED)
        history = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))
        self.assertEqual(history[0]['body'], 'Review my essay outline.')
        self.client.force_authenticate(self.student_b_user)
        other = self.client.post('/api/message-channels/saved/', {}, format='json')
        self.assertNotEqual(other.data['id'], channel_id)
        self.assertEqual(self.client.get(f'/api/message-channels/{channel_id}/').status_code, 404)
        self.assertEqual(self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}')), [])
        self.assertEqual(self.client.post('/api/channel-messages/', {
            'channel': channel_id, 'body': 'Not my notes.',
        }, format='json').status_code, 400)

    def test_direct_chat_search_finds_contact_names(self):
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertIn('id', opened.data)
        found = self.results(self.client.get('/api/message-channels/', {
            'kind': 'direct', 'search': self.counselor.username,
        }))
        self.assertEqual([item['id'] for item in found], [opened.data['id']])
        self.assertEqual(self.results(self.client.get('/api/message-channels/', {
            'kind': 'direct', 'search': 'nonexistent-contact-xyz',
        })), [])

    def test_direct_channel_is_unique_and_private_to_its_members(self):
        self.client.force_authenticate(self.student_a_user)
        first = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        second = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        channel = MessageChannel.objects.get(id=first.data['id'])
        self.assertEqual(channel.kind, MessageChannel.Kind.DIRECT)
        self.assertEqual(channel.memberships.count(), 2)
        exposed = self.client.patch(
            f'/api/message-channels/{channel.id}/',
            {'is_public': True},
            format='json',
        )
        self.assertEqual(exposed.status_code, status.HTTP_400_BAD_REQUEST)

        sent = self.client.post(
            '/api/channel-messages/',
            {'channel': channel.id, 'body': 'Private direct message.'},
            format='json',
        )
        self.assertEqual(sent.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_b_user)
        listed = self.results(self.client.get('/api/message-channels/?kind=direct'))
        self.assertEqual(listed, [])
        messages = self.results(self.client.get(f'/api/channel-messages/?channel={channel.id}'))
        self.assertEqual(messages, [])

    def test_direct_message_reply_round_trip_and_read_receipt(self):
        self.client.force_authenticate(self.student_a_user)
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        channel_id = opened.data['id']
        sent = self.client.post('/api/channel-messages/', {
            'channel': channel_id, 'body': 'Can you review my draft?', 'is_anonymous': False,
        }, format='json')
        self.assertEqual(sent.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sent.data['sender_id'], self.student_a_user.id)
        self.assertEqual(sent.data['channel'], channel_id)

        self.client.force_authenticate(self.counselor)
        inbox = self.results(self.client.get('/api/message-channels/?kind=direct'))
        self.assertEqual(inbox[0]['unread_count'], 1)
        self.assertEqual(inbox[0]['last_message']['body'], sent.data['body'])
        reply = self.client.post('/api/channel-messages/', {
            'channel': channel_id, 'body': 'Send the draft here.',
            'parent': sent.data['id'], 'is_anonymous': False,
        }, format='json')
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reply.data['parent_preview']['body'], sent.data['body'])

        self.client.force_authenticate(self.student_a_user)
        history = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}&page_size=50'))
        self.assertEqual([item['id'] for item in history], [reply.data['id'], sent.data['id']])
        read = self.client.post(f'/api/message-channels/{channel_id}/mark-read/', {}, format='json')
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        inbox = self.results(self.client.get('/api/message-channels/?kind=direct'))
        self.assertEqual(inbox[0]['unread_count'], 0)

    def test_student_can_message_only_own_school_staff_when_user_school_is_empty(self):
        other_school_staff = User.objects.create_user(
            username='organization-b-messaging',
            email='organization-b-messaging@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_b,
        )
        self.student_a_user.school = None
        self.student_a_user.save(update_fields=['school'])

        self.client.force_authenticate(self.student_a_user)
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(contacts.status_code, status.HTTP_200_OK)
        contact_ids = {item['id'] for item in contacts.data}
        self.assertTrue({self.counselor.id, self.teacher.id, self.organization.id}.issubset(contact_ids))
        self.assertNotIn(self.student_b_user.id, contact_ids)
        self.assertNotIn(other_school_staff.id, contact_ids)

        first = self.client.post('/api/message-channels/direct/', {'user': self.organization.id}, format='json')
        second = self.client.post('/api/message-channels/direct/', {'user': self.organization.id}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        channel = MessageChannel.objects.get(id=first.data['id'])
        self.assertEqual(channel.school, self.school_a)
        self.assertEqual(channel.memberships.count(), 2)

        blocked = self.client.post('/api/message-channels/direct/', {'user': other_school_staff.id}, format='json')
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)

    def test_counselor_messaging_contacts_are_limited_to_assigned_students_and_school_staff(self):
        outsider = User.objects.create_user(
            username='unrelated-student',
            email='unrelated-student@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_b,
        )
        self.client.force_authenticate(self.counselor)
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(contacts.status_code, status.HTTP_200_OK)
        contact_ids = {item['id'] for item in contacts.data}
        self.assertTrue({self.student_a_user.id, self.organization.id, self.teacher.id}.issubset(contact_ids))
        self.assertNotIn(self.student_b_user.id, contact_ids)
        self.assertNotIn(outsider.id, contact_ids)

    def test_school_messaging_interface_supports_counselor_contact_overview_and_member_management(self):
        self.client.force_authenticate(self.organization)
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(contacts.status_code, status.HTTP_200_OK)
        contact_ids = {item['id'] for item in contacts.data}
        self.assertTrue({self.student_a_user.id, self.teacher.id, self.counselor.id}.issubset(contact_ids))
        self.assertNotIn(self.student_b_user.id, contact_ids)

        direct = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertEqual(direct.status_code, status.HTTP_201_CREATED)
        group = self.client.post(
            '/api/message-channels/',
            {
                'kind': MessageChannel.Kind.GROUP,
                'name': 'School A staff and students',
                'members': [self.student_a_user.id, self.counselor.id, self.student_b_user.id],
            },
            format='json',
        )
        self.assertEqual(group.status_code, status.HTTP_201_CREATED)
        channel = MessageChannel.objects.get(id=group.data['id'])
        self.assertTrue(channel.memberships.filter(user=self.student_a_user).exists())
        self.assertTrue(channel.memberships.filter(user=self.counselor).exists())
        self.assertFalse(channel.memberships.filter(user=self.student_b_user).exists())

        members = self.client.get(f'/api/message-channels/{channel.id}/members/')
        self.assertEqual(members.status_code, status.HTTP_200_OK)
        removed = self.client.delete(
            f'/api/message-channels/{channel.id}/members/',
            {'user': self.student_a_user.id},
            format='json',
        )
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(channel.memberships.filter(user=self.student_a_user).exists())

        overview = self.client.get('/api/message-channels/overview/')
        self.assertEqual(overview.status_code, status.HTTP_200_OK)
        self.assertEqual(overview.data['channel_counts'][MessageChannel.Kind.DIRECT], 1)
        self.assertEqual(overview.data['channel_counts'][MessageChannel.Kind.GROUP], 1)
        self.assertEqual(overview.data['students_total'], 1)

    def test_teacher_group_is_school_scoped_and_tracks_unread(self):
        self.client.force_authenticate(self.teacher)
        created = self.client.post(
            '/api/message-channels/',
            {
                'kind': MessageChannel.Kind.GROUP,
                'name': 'School A application group',
                'members': [self.student_a_user.id, self.student_b_user.id],
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        channel = MessageChannel.objects.get(id=created.data['id'])
        self.assertEqual(channel.school, self.school_a)
        self.assertTrue(channel.memberships.filter(user=self.student_a_user).exists())
        self.assertFalse(channel.memberships.filter(user=self.student_b_user).exists())
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel.id, 'body': 'Group deadline update.'},
            format='json',
        )
        self.assertEqual(message.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        group = self.results(self.client.get('/api/message-channels/?kind=group'))[0]
        self.assertEqual(group['unread_count'], 1)
        marked = self.client.post(f'/api/message-channels/{channel.id}/mark-read/', {}, format='json')
        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        group = self.results(self.client.get('/api/message-channels/?kind=group'))[0]
        self.assertEqual(group['unread_count'], 0)

        self.client.force_authenticate(self.student_b_user)
        self.assertEqual(self.results(self.client.get('/api/message-channels/?kind=group')), [])

    def test_community_requires_join_before_posting(self):
        self.client.force_authenticate(self.teacher)
        created = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.COMMUNITY, 'name': 'School A Community'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        channel_id = created.data['id']

        self.client.force_authenticate(self.student_a_user)
        community = self.results(self.client.get('/api/message-channels/?kind=community'))[0]
        self.assertFalse(community['is_member'])
        blocked = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Posting before joining.'},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        joined = self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.assertEqual(joined.status_code, status.HTTP_201_CREATED)
        posted = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Hello community.'},
            format='json',
        )
        self.assertEqual(posted.status_code, status.HTTP_201_CREATED)

    def test_discussion_supports_anonymous_threads_and_accepted_answer(self):
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'How should I structure my essay?'},
            format='json',
        )
        self.assertEqual(discussion.status_code, status.HTTP_201_CREATED)
        channel_id = discussion.data['id']
        question = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'I need a clear outline.', 'is_anonymous': True},
            format='json',
        )
        self.assertEqual(question.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.organization)
        joined = self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.assertIn(joined.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        visible_question = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))[0]
        self.assertIsNone(visible_question['sender_id'])
        self.assertEqual(visible_question['sender_name'], 'Anonymous')
        reply = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'parent': question.data['id'], 'body': 'Start with one concrete moment.'},
            format='json',
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        root_answer = self.client.post(f"/api/channel-messages/{question.data['id']}/accept/", {}, format='json')
        self.assertEqual(root_answer.status_code, status.HTTP_400_BAD_REQUEST)
        accepted = self.client.post(f"/api/channel-messages/{reply.data['id']}/accept/", {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertTrue(accepted.data['is_accepted_answer'])
        self.assertEqual(ChannelMessage.objects.filter(channel_id=channel_id, is_accepted_answer=True).count(), 1)

    def test_anonymous_author_stays_hidden_and_student_can_report_once(self):
        classmate = User.objects.create_user(
            username='student-a-classmate',
            email='student-a-classmate@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=classmate, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'Private identity discussion'},
            format='json',
        )
        channel_id = discussion.data['id']
        own_message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'My own question.'},
            format='json',
        )

        self.client.force_authenticate(classmate)
        self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        anonymous_message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Anonymous classmate reply.', 'is_anonymous': True},
            format='json',
        )
        self.assertEqual(anonymous_message.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.student_a_user)
        listed = self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))
        visible = next(item for item in listed if item['id'] == anonymous_message.data['id'])
        self.assertIsNone(visible['sender_id'])
        self.assertEqual(visible['sender_name'], 'Anonymous')
        reported = self.client.post(
            f"/api/channel-messages/{anonymous_message.data['id']}/report/",
            {'reason': MessageReport.Reason.HARASSMENT, 'details': 'Please review this message.'},
            format='json',
        )
        self.assertEqual(reported.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(
            f"/api/channel-messages/{anonymous_message.data['id']}/report/",
            {'reason': MessageReport.Reason.SPAM},
            format='json',
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        own_report = self.client.post(
            f"/api/channel-messages/{own_message.data['id']}/report/",
            {'reason': MessageReport.Reason.OTHER},
            format='json',
        )
        self.assertEqual(own_report.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get('/api/message-reports/').status_code, status.HTTP_403_FORBIDDEN)

    def test_school_moderator_queue_reveals_identity_only_there_and_removes_content(self):
        classmate = User.objects.create_user(
            username='reported-classmate',
            email='reported-classmate@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=classmate, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.student_a_user)
        discussion = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.DISCUSSION, 'name': 'Moderated school discussion'},
            format='json',
        )
        channel_id = discussion.data['id']
        self.client.force_authenticate(classmate)
        self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'Message for moderation.', 'is_anonymous': True},
            format='json',
        )
        self.client.force_authenticate(self.student_a_user)
        report = self.client.post(
            f"/api/channel-messages/{message.data['id']}/report/",
            {'reason': MessageReport.Reason.PRIVACY},
            format='json',
        )

        unrelated_school = User.objects.create_user(
            username='organization-b',
            email='organization-b@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_b,
        )
        self.client.force_authenticate(unrelated_school)
        self.assertEqual(self.client.get('/api/message-reports/?status=pending').status_code, status.HTTP_403_FORBIDDEN)

        ChannelMembership.objects.create(
            channel_id=channel_id,
            user=self.organization,
            role=ChannelMembership.Role.MODERATOR,
        )
        self.client.force_authenticate(self.organization)
        feed_message = next(
            item for item in self.results(self.client.get(f'/api/channel-messages/?channel={channel_id}'))
            if item['id'] == message.data['id']
        )
        self.assertIsNone(feed_message['sender_id'])
        queue = self.results(self.client.get('/api/message-reports/?status=pending'))
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['sender_id'], classmate.id)
        self.assertEqual(queue[0]['reporter'], self.student_a_user.id)
        resolved = self.client.post(
            f"/api/message-reports/{report.data['id']}/resolve/",
            {'action': MessageReport.Action.CONTENT_REMOVED, 'moderator_note': 'Removed after review.'},
            format='json',
        )
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)
        self.assertEqual(resolved.data['status'], MessageReport.Status.RESOLVED)
        self.assertEqual(resolved.data['action'], MessageReport.Action.CONTENT_REMOVED)
        self.assertIsNotNone(resolved.data['message_deleted_at'])

    def test_moderator_mute_blocks_new_channel_messages(self):
        reporter = User.objects.create_user(
            username='same-school-reporter',
            email='same-school-reporter@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        StudentProfile.objects.create(user=reporter, school=self.school_a, school_name=self.school_a.name)
        self.client.force_authenticate(self.teacher)
        community = self.client.post(
            '/api/message-channels/',
            {'kind': MessageChannel.Kind.COMMUNITY, 'name': 'School moderation community'},
            format='json',
        )
        channel_id = community.data['id']
        for member in [self.student_a_user, reporter]:
            self.client.force_authenticate(member)
            self.client.post(f'/api/message-channels/{channel_id}/join/', {}, format='json')
        self.client.force_authenticate(self.student_a_user)
        message = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'A reported community message.'},
            format='json',
        )
        self.client.force_authenticate(reporter)
        report = self.client.post(
            f"/api/channel-messages/{message.data['id']}/report/",
            {'reason': MessageReport.Reason.SPAM},
            format='json',
        )
        self.client.force_authenticate(self.teacher)
        muted = self.client.post(
            f"/api/message-reports/{report.data['id']}/resolve/",
            {'action': MessageReport.Action.MUTED_24H},
            format='json',
        )
        self.assertEqual(muted.status_code, status.HTTP_200_OK)
        membership = ChannelMembership.objects.get(channel_id=channel_id, user=self.student_a_user)
        self.assertGreater(membership.muted_until, timezone.now() + timedelta(hours=23))
        self.client.force_authenticate(self.student_a_user)
        blocked = self.client.post(
            '/api/channel-messages/',
            {'channel': channel_id, 'body': 'This should be blocked while muted.'},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replying_marks_the_conversation_read(self):
        self.client.force_authenticate(self.student_a_user)
        channel_id = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id},
                                      format='json').data['id']
        self.client.post('/api/channel-messages/', {'channel': channel_id, 'body': 'Hi'}, format='json')
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get('/api/message-channels/overview/').data['unread_total'], 1)
        self.client.post('/api/channel-messages/', {'channel': channel_id, 'body': 'Hello'}, format='json')
        self.assertEqual(self.client.get('/api/message-channels/overview/').data['unread_total'], 0)
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get('/api/message-channels/overview/').data['unread_total'], 1)
