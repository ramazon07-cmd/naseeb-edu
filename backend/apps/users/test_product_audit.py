from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.audit import audit_product_action
from apps.users.models import ProductAuditEvent, User


class ProductAuditTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Audit School', code='audit-school')
        self.other_school = School.objects.create(name='Audit Other', code='audit-other')
        self.admin = User.objects.create_user(
            username='audit-admin', email='audit-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.counselor = User.objects.create_user(
            username='audit-counselor', email='audit-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.student_user = User.objects.create_user(
            username='audit-student', email='audit-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, school=self.school, school_name=self.school.name,
            assigned_counselor=self.counselor,
        )

    def events(self, action):
        return ProductAuditEvent.objects.filter(action=action)

    def test_an_audit_event_is_a_single_insert_that_carries_the_school(self):
        with self.assertNumQueries(1):
            event = audit_product_action(actor=self.admin, action='test.event', target=self.student_user)
        self.assertEqual(event.school_id, self.school.id)
        school_event = audit_product_action(actor=self.admin, action='test.school', target=self.school)
        self.assertEqual(school_event.school_id, self.school.id)

    def test_staff_reads_of_student_data_are_audited(self):
        self.client.force_authenticate(self.admin)
        self.client.get(f'/api/students/{self.student.id}/')
        self.client.get(f'/api/students/{self.student.id}/data-visibility/')
        self.client.get(f'/api/students/{self.student.id}/xp-history/')
        self.client.get(f'/api/students/{self.student.id}/photo/')
        self.client.get(f'/api/users/accounts/{self.student_user.id}/')
        for action in (
            'student_360.viewed', 'student_visibility.viewed', 'student_xp.viewed',
            'student_photo.viewed', 'student_account.viewed',
        ):
            event = self.events(action).get()
            self.assertEqual(event.actor, self.admin)
            self.assertEqual(event.school_id, self.school.id)

    def test_school_staff_reading_their_own_students_are_not_product_audited(self):
        self.client.force_authenticate(self.counselor)
        self.client.get(f'/api/students/{self.student.id}/')
        self.client.get(f'/api/students/{self.student.id}/xp-history/')
        self.client.get(f'/api/users/accounts/{self.student_user.id}/')
        self.assertFalse(ProductAuditEvent.objects.exists())

    def test_deactivation_move_credentials_and_parent_invites_are_audited(self):
        self.client.force_authenticate(self.admin)
        moved = self.client.patch(
            f'/api/users/accounts/{self.student_user.id}/', {'school': self.other_school.id}, format='json',
        )
        self.assertEqual(moved.status_code, status.HTTP_200_OK)
        move = self.events('student.moved').get()
        self.assertEqual(
            (move.metadata['from_school'], move.metadata['to_school']), (self.school.id, self.other_school.id),
        )
        self.assertEqual(move.school_id, self.other_school.id)

        self.client.patch(f'/api/users/accounts/{self.student_user.id}/', {'is_active': False}, format='json')
        # A student's deactivation is recorded once, by the tenancy service.
        self.assertEqual(self.events('student.deactivated').count(), 1)
        self.assertFalse(self.events('account.deactivated').exists())

        self.client.force_authenticate(self.counselor)
        other = User.objects.create_user(
            username='audit-second', email='audit-second@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        second = StudentProfile.objects.create(
            user=other, school=self.school, school_name=self.school.name, assigned_counselor=self.counselor,
        )
        issued = self.client.post(f'/api/users/accounts/{other.id}/temporary-credential/', {}, format='json')
        self.assertEqual(issued.status_code, status.HTTP_200_OK)
        credential = self.events('credential.issued').get()
        self.assertEqual((credential.actor, credential.school_id), (self.counselor, self.school.id))

        invited = self.client.post('/api/parent-links/invite/', {
            'student': second.id, 'email': 'parent@example.com', 'password': 'StrongPass123!',
            'relationship': 'mother',
        }, format='json')
        self.assertEqual(invited.status_code, status.HTTP_201_CREATED, invited.data)
        invite = self.events('parent.invited').get()
        self.assertEqual(invite.school_id, self.school.id)
        self.assertEqual(invite.metadata['student'], second.id)

    def account_patch(self, account, payload):
        ProductAuditEvent.objects.all().delete()
        response = self.client.patch(f'/api/users/accounts/{account.id}/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return list(ProductAuditEvent.objects.values_list('action', flat=True))

    def test_each_account_change_by_an_admin_is_audited_once(self):
        teacher = User.objects.create_user(
            username='audit-teacher', email='audit-teacher@example.com', password='StrongPass123!',
            role=User.Role.TEACHER, school=self.school,
        )
        self.client.force_authenticate(self.admin)
        student = self.student_user
        cases = [
            (student, {'school': self.other_school.id}, ['student.moved']),
            (student, {'is_active': False}, ['student.deactivated']),
            (student, {'is_active': True}, ['student.reactivated']),
            (student, {'first_name': 'Renamed'}, ['account.updated']),
            # Nothing changes school or activation: a plain update.
            (student, {'school': self.other_school.id, 'is_active': True}, ['account.updated']),
            (student, {'school': self.school.id, 'first_name': 'Moved'}, ['student.moved']),
            (teacher, {'school': self.other_school.id}, ['account.moved']),
            (teacher, {'is_active': False}, ['account.deactivated']),
            (teacher, {'last_name': 'Renamed'}, ['account.updated']),
            (self.counselor, {'first_name': 'Renamed'}, ['counselor.updated']),
        ]
        for account, payload, expected in cases:
            with self.subTest(account=account.username, payload=payload):
                self.assertEqual(self.account_patch(account, payload), expected)

    def test_a_repeated_parent_invitation_is_audited_once(self):
        self.client.force_authenticate(self.counselor)
        payload = {
            'student': self.student.id, 'email': 'twice@example.com', 'password': 'StrongPass123!',
            'relationship': 'father',
        }
        for _ in range(2):
            self.assertEqual(self.client.post('/api/parent-links/invite/', payload, format='json').status_code, 201)
        invite = self.events('parent.invited').get()
        self.assertTrue(invite.metadata['created_account'])

    def test_school_create_and_update_are_audited_with_the_school(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post('/api/schools/', {'name': 'Fresh', 'code': 'fresh'}, format='json')
        self.client.patch(f'/api/schools/{created.data["id"]}/', {'contact_phone': '+998'}, format='json')
        for action in ('school.created', 'school.updated'):
            self.assertEqual(self.events(action).get().school_id, created.data['id'])


class AuditListTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='List School', code='list-school')
        self.other = School.objects.create(name='List Other', code='list-other')
        self.admin = User.objects.create_user(
            username='list-admin', email='list-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.support = User.objects.create_user(
            username='list-support', email='list-support@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.SUPPORT,
        )
        for index in range(30):
            audit_product_action(actor=self.admin, action='student_360.viewed', target=self.school)
        audit_product_action(actor=self.support, action='support.profile_viewed', target=self.other)
        old = audit_product_action(actor=self.admin, action='school.updated', target=self.other)
        ProductAuditEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))

    def fetch(self, **params):
        self.client.force_authenticate(self.support)
        return self.client.get('/api/users/audit-events/', params)

    def test_list_is_paginated_in_constant_queries(self):
        self.client.force_authenticate(self.support)
        with self.assertNumQueries(2):
            response = self.client.get('/api/users/audit-events/', {'page_size': 10})
        self.assertEqual(response.data['count'], 32)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIsNotNone(response.data['next'])
        self.assertEqual(response.data['results'][0]['school_name'], 'List Other')

    def test_filters_by_actor_action_school_and_date(self):
        self.assertEqual(self.fetch(actor=self.support.id).data['count'], 1)
        self.assertEqual(self.fetch(action='student_360').data['count'], 30)
        self.assertEqual(self.fetch(action='student_360.viewed').data['count'], 30)
        self.assertEqual(self.fetch(school=self.other.id).data['count'], 2)
        today = timezone.localdate().isoformat()
        self.assertEqual(self.fetch(school=self.other.id, date_from=today).data['count'], 1)
        old_day = (timezone.localdate() - timedelta(days=40)).isoformat()
        self.assertEqual(self.fetch(date_to=old_day).data['count'], 1)

    def test_cursor_pages_keep_the_filters(self):
        today = timezone.localdate().isoformat()
        first = self.fetch(cursor='', page_size=20, ordering='-created', action='student_360', date_from=today)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(len(first.data['results']), 20)
        self.assertIsNotNone(first.data['next'])
        cursor = parse_qs(urlparse(first.data['next']).query)['cursor'][0]
        second = self.fetch(cursor=cursor, page_size=20, ordering='-created', action='student_360', date_from=today)
        self.assertEqual(len(second.data['results']), 10)
        self.assertIsNone(second.data['next'])
        ids = [row['id'] for row in first.data['results'] + second.data['results']]
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(self.fetch(cursor='', search='list-support', school=self.other.id).data['results'][0]['action'], 'support.profile_viewed')

    def test_invalid_dates_are_rejected(self):
        response = self.fetch(date_from='yesterday')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_audit_log_is_staff_only(self):
        counselor = User.objects.create_user(
            username='list-counselor', email='list-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.client.force_authenticate(counselor)
        self.assertEqual(self.client.get('/api/users/audit-events/').status_code, status.HTTP_403_FORBIDDEN)
