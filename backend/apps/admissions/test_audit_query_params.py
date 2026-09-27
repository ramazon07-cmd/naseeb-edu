"""Malformed query/body parameters must produce a 4xx, never a 500.

Covers every id-like parameter that the views parse (query string and JSON
body), plus other free-form parameters that reach the ORM.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import (
    ChannelMembership, ChannelMessage, CounselorRoadmap, CounselorRoadmapTemplate, MessageChannel,
)

from .test_audit_base import AuditBaseMixin

NON_NUMERIC = ('abc', '1.5', '1e3', '0x10', '--1', '1;DROP')
ODD_BUT_HARMLESS = ('-1', '0', '%20', '')



class QueryStringIdTests(AuditBaseMixin, APITestCase):
    ADMIN_LISTS = (
        '/api/applications/?student={}',
        '/api/tasks/?student={}',
        '/api/documents/?student={}',
        '/api/roadmap-missions/?student={}',
        '/api/challenge-attempts/?student={}',
        '/api/counselor-roadmaps/?counselor={}',
        '/api/counselor-roadmaps/?school={}',
        '/api/users/accounts/?school={}',
        '/api/students/assignment-candidates/?counselor={}',
    )

    def setUp(self):
        super().setUp()
        self.room = MessageChannel.objects.create(kind='community', name='Room', school=self.school_a, is_public=True)
        ChannelMembership.objects.create(channel=self.room, user=self.counselor)
        ChannelMessage.objects.create(channel=self.room, sender=self.counselor, body='hi')

    def assert_400(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, f'{url} -> {response.status_code}')

    def assert_not_500(self, url):
        response = self.client.get(url)
        self.assertLess(response.status_code, 500, url)

    def test_admin_list_filters_reject_non_numeric_ids(self):
        self.client.force_authenticate(self.admin)
        for template in self.ADMIN_LISTS:
            for value in NON_NUMERIC:
                self.assert_400(template.format(value))

    def test_counselor_list_filters_reject_non_numeric_ids(self):
        self.client.force_authenticate(self.counselor)
        for url in (
            '/api/applications/?student=abc', '/api/tasks/?student=abc', '/api/documents/?student=abc',
            '/api/roadmap-missions/?student=abc', '/api/challenge-attempts/?student=abc',
        ):
            self.assert_400(url)

    def test_channel_message_filters_reject_non_numeric_ids(self):
        self.client.force_authenticate(self.counselor)
        self.assert_400('/api/channel-messages/?channel=abc')
        self.assert_400(f'/api/channel-messages/?channel={self.room.id}&parent=abc')
        ok = self.client.get(f'/api/channel-messages/?channel={self.room.id}')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_harmless_odd_values_do_not_500(self):
        self.client.force_authenticate(self.admin)
        for template in self.ADMIN_LISTS:
            for value in ODD_BUT_HARMLESS:
                self.assert_not_500(template.format(value))

    def test_out_of_range_integers_do_not_500(self):
        """Ids larger than a signed 64-bit integer.

        The SQLite driver raises OverflowError on them (a 500), while PostgreSQL
        quietly returns nothing, so int_param bounds ids to the 64-bit range.
        """
        huge = str(2 ** 70)
        self.client.force_authenticate(self.admin)
        for template in self.ADMIN_LISTS:
            self.assert_not_500(template.format(huge))
        self.assert_not_500(f'/api/channel-messages/?channel={huge}')

    def test_other_free_form_parameters_do_not_500(self):
        self.client.force_authenticate(self.admin)
        for url in (
            '/api/applications/?status=not-a-status',
            '/api/tasks/?status=bogus&priority=bogus',
            '/api/documents/?status=%27',
            '/api/notifications/?unread=maybe',
            '/api/counselor-roadmap-templates/?kind=bogus&is_active=maybe',
            '/api/counselor-roadmaps/?status=bogus',
            '/api/message-channels/?kind=bogus&search=%25_',
            '/api/message-reports/?status=bogus',
            '/api/schools/?is_active=maybe&workspace_type=bogus',
            '/api/users/accounts/?role=bogus&is_active=maybe',
            '/api/screen-time/summary/?days=abc',
            '/api/screen-time/summary/?days=-5',
            '/api/screen-time/summary/?days=99999999999999999999999',
            '/api/students/?page=abc',
            '/api/students/?page=999',
        ):
            self.assert_not_500(url)

    def test_nul_byte_in_string_parameters_does_not_500(self):
        """A NUL byte (%00) in any free-text query parameter.

        psycopg raises DataError for NUL in text (a 500 on PostgreSQL only;
        SQLite accepts it).
        """
        self.client.force_authenticate(self.admin)
        broken = []
        for url in (
            '/api/message-channels/?search=a%00b',
            '/api/counselor-roadmap-templates/?search=a%00b',
            '/api/message-reports/?search=a%00b',
            '/api/schools/?search=a%00b',
            '/api/users/accounts/?search=a%00b',
            '/api/message-channels/contacts/?search=a%00b',
            '/api/applications/?status=a%00b',
            '/api/message-channels/?kind=a%00b',
        ):
            try:
                code = self.client.get(url).status_code
            except Exception as exc:  # DEBUG=True test client re-raises
                code = type(exc).__name__
            # An unknown choice (the NUL is stripped) is a validation error.
            if not isinstance(code, int) or code >= 500:
                broken.append((url, code))
        self.assertEqual(broken, [])

    def test_detail_routes_with_non_numeric_pk_are_404(self):
        self.client.force_authenticate(self.admin)
        for url in ('/api/students/abc/', '/api/students/abc/xp-history/', '/api/challenge-attempts/abc/',
                    '/api/message-reports/abc/', '/api/activity/abc/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, url)


class BodyIdTests(AuditBaseMixin, APITestCase):
    def post(self, user, url, data, method='post'):
        self.client.force_authenticate(user)
        return getattr(self.client, method)(url, data, format='json')

    def assert_client_error(self, response, label, expected=status.HTTP_400_BAD_REQUEST):
        self.assertEqual(response.status_code, expected, f'{label}: {response.status_code} {response.data}')

    def test_student_assignment_and_quick_create(self):
        self.assert_client_error(self.post(
            self.admin, '/api/students/assign-counselor/', {'students': [self.student.id], 'counselor': 'abc'},
        ), 'assign counselor (admin)')
        self.assert_client_error(self.post(
            self.counselor, '/api/students/assign-counselor/', {'students': [self.student.id], 'counselor': 'abc'},
        ), 'assign counselor (counselor)')
        self.assert_client_error(self.post(
            self.counselor, '/api/students/assign-counselor/', {'students': ['abc']},
        ), 'assign counselor students list')
        for user in (self.admin, self.counselor):
            self.assert_client_error(self.post(user, '/api/students/quick-create/', {
                'name': 'Quick Student', 'password': 'Very-Strong-Pass-918!', 'school': 'abc',
            }), f'quick-create ({user.username})')
        # A JSON boolean is not an id either.
        self.assert_client_error(self.post(self.admin, '/api/students/quick-create/', {
            'name': 'Quick Student', 'password': 'Very-Strong-Pass-918!', 'school': True,
        }), 'quick-create bool school')

    def test_roadmap_actions(self):
        self.assert_client_error(self.post(
            self.counselor, '/api/roadmap-missions/extend-level-one/', {'student': 'abc'},
        ), 'extend-level-one')
        self.assert_client_error(self.post(
            self.counselor, '/api/counselor-roadmaps/', {'template': 'abc'},
        ), 'counselor roadmap template')
        template = CounselorRoadmapTemplate.objects.create(name='T', kind='professional_onboarding')
        roadmap = CounselorRoadmap.objects.create(
            counselor=self.counselor, school=self.school_a, template=template, title='R',
            kind='professional_onboarding',
        )
        self.assert_client_error(self.post(
            self.counselor, f'/api/counselor-roadmaps/{roadmap.id}/submit-mission/',
            {'mission': 'abc', 'counselor_note': 'done'},
        ), 'submit-mission')
        self.assert_client_error(self.post(
            self.admin, f'/api/counselor-roadmaps/{roadmap.id}/review-mission/',
            {'mission': 'abc', 'decision': 'approve'},
        ), 'review-mission')

    def test_messaging_actions(self):
        self.assert_client_error(self.post(
            self.counselor, '/api/student-messages/', {'student': 'abc', 'body': 'hello'},
        ), 'student message')
        self.assert_client_error(self.post(
            self.counselor, '/api/message-channels/direct/', {'user': 'abc'},
        ), 'direct')
        room = MessageChannel.objects.create(kind='group', name='G', school=self.school_a)
        ChannelMembership.objects.create(channel=room, user=self.counselor, role=ChannelMembership.Role.OWNER)
        self.assert_client_error(self.post(
            self.counselor, f'/api/message-channels/{room.id}/members/', {'user': 'abc'},
        ), 'add member')
        self.assert_client_error(self.post(
            self.counselor, f'/api/message-channels/{room.id}/members/', {'user': 'abc'}, method='delete',
        ), 'remove member')
        self.assert_client_error(self.post(
            self.counselor, '/api/message-channels/',
            {'kind': 'group', 'name': 'Bad', 'members': 'not-a-list'},
        ), 'channel members not a list')
