from importlib import import_module

from django.apps import apps as django_apps
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile, SupportTicket
from apps.users.auth_views import token_pair_for_user
from apps.users.models import ProductAuditEvent, User


def staff(username, tier):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass123!',
        role=User.Role.ADMIN, admin_tier=tier,
    )


class StaffTierTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Tier School', code='tier-school')
        self.support = staff('support', User.AdminTier.SUPPORT)
        self.ops = staff('ops', User.AdminTier.OPS)
        self.superadmin = staff('superadmin', User.AdminTier.SUPERADMIN)
        self.student = User.objects.create_user(
            username='tier-student', email='tier-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school, school_name=self.school.name)
        self.counselor_payload = {
            'username': 'tier-counselor', 'email': 'tier-counselor@example.com', 'first_name': 'Tier',
            'password': 'StrongPass123!', 'school': self.school.id,
        }

    def login(self, user):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_pair_for_user(user)["access"]}')

    def test_admins_without_an_explicit_tier_keep_full_access(self):
        legacy = User.objects.create_user(
            username='legacy-admin', email='legacy-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.assertEqual(legacy.admin_tier, User.AdminTier.SUPERADMIN)
        User.objects.filter(pk=legacy.pk).update(admin_tier='')
        import_module('apps.users.migrations.0007_admin_staff_tiers').map_existing_admins(django_apps, None)
        legacy.refresh_from_db()
        self.assertEqual(legacy.admin_tier, User.AdminTier.SUPERADMIN)

    def test_non_staff_accounts_never_carry_a_tier(self):
        counselor = User.objects.create_user(
            username='tierless', email='tierless@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school, admin_tier=User.AdminTier.SUPERADMIN,
        )
        self.assertEqual(counselor.admin_tier, '')
        self.assertEqual(counselor.staff_tier, '')

    def test_support_reads_resets_credentials_and_views_audit(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get('/api/users/accounts/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/users/audit-events/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f'/api/students/{self.profile.id}/').status_code, status.HTTP_200_OK)
        reset = self.client.post(f'/api/users/accounts/{self.student.id}/temporary-credential/', {}, format='json')
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

    def test_support_cannot_manage_workspaces_or_accounts(self):
        self.client.force_authenticate(self.support)
        denied = [
            self.client.post('/api/schools/', {'name': 'New', 'code': 'new'}, format='json'),
            self.client.post('/api/users/accounts/create-counselor/', self.counselor_payload, format='json'),
            self.client.post(f'/api/users/accounts/{self.student.id}/deactivate/'),
            self.client.patch(f'/api/users/accounts/{self.student.id}/', {'phone': '1'}, format='json'),
            self.client.delete(f'/api/users/accounts/{self.student.id}/'),
        ]
        self.assertEqual({response.status_code for response in denied}, {status.HTTP_403_FORBIDDEN})
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_support_writes_outside_its_routes_are_rejected_centrally(self):
        self.login(self.support)
        response = self.client.post('/api/tasks/', {'title': 'Staff task', 'student': self.profile.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'staff_tier_forbidden')
        reset = self.client.post(f'/api/users/accounts/{self.student.id}/temporary-credential/', {}, format='json')
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

    def test_ops_manages_schools_and_counselors(self):
        self.login(self.ops)
        created = self.client.post('/api/schools/', {'name': 'Ops School', 'code': 'ops-school'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        counselor = self.client.post('/api/users/accounts/create-counselor/', self.counselor_payload, format='json')
        self.assertEqual(counselor.status_code, status.HTTP_201_CREATED)

    def test_ops_cannot_use_superadmin_only_routes(self):
        self.login(self.ops)
        response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Ops template', 'kind': 'school_management', 'missions': [],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'staff_tier_forbidden')

    def test_only_superadmin_grants_admin_role_or_changes_tiers(self):
        self.client.force_authenticate(self.ops)
        promote = self.client.patch(f'/api/users/accounts/{self.student.id}/', {'role': 'admin'}, format='json')
        self.assertEqual(promote.status_code, status.HTTP_400_BAD_REQUEST)
        # Another staff account is off limits below super admin altogether.
        raise_tier = self.client.patch(f'/api/users/accounts/{self.support.id}/', {'admin_tier': 'ops'}, format='json')
        self.assertEqual(raise_tier.status_code, status.HTTP_403_FORBIDDEN)
        self_raise = self.client.patch(f'/api/users/accounts/{self.ops.id}/', {'admin_tier': 'superadmin'}, format='json')
        self.assertEqual(self_raise.status_code, status.HTTP_400_BAD_REQUEST)
        self.support.refresh_from_db()
        self.assertEqual(self.support.admin_tier, User.AdminTier.SUPPORT)

        self.client.force_authenticate(self.superadmin)
        changed = self.client.patch(f'/api/users/accounts/{self.support.id}/', {'admin_tier': 'ops'}, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.support.refresh_from_db()
        self.assertEqual(self.support.admin_tier, User.AdminTier.OPS)

    def test_superadmin_writes_anywhere(self):
        self.login(self.superadmin)
        response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Super template', 'kind': 'school_management',
            'missions': [{'title': 'Kickoff', 'sequence': 1, 'due_days': 3, 'is_required': True}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_lower_tiers_cannot_change_or_open_other_staff_accounts(self):
        root = User.objects.create_superuser('tier-root', 'tier-root@example.com', 'StrongPass123!')
        self.login(self.ops)
        for target in (self.superadmin, root, self.support):
            responses = [
                self.client.post(f'/api/users/accounts/{target.id}/deactivate/'),
                self.client.patch(
                    f'/api/users/accounts/{target.id}/',
                    {'email': 'taken-over@example.com', 'username': 'taken-over', 'is_active': False}, format='json',
                ),
                self.client.delete(f'/api/users/accounts/{target.id}/'),
                self.client.post(
                    f'/api/users/accounts/{target.id}/support-view/', {'reason': 'Checking this staff account'}, format='json',
                ),
            ]
            for response in responses:
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, target.username)
                self.assertEqual(response.data['code'], 'staff_tier_forbidden')
            target.refresh_from_db()
            self.assertTrue(target.is_active)
            self.assertNotEqual(target.email, 'taken-over@example.com')

        self.login(self.support)
        view = self.client.post(
            f'/api/users/accounts/{self.ops.id}/support-view/', {'reason': 'Checking this staff account'}, format='json',
        )
        self.assertEqual(view.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProductAuditEvent.objects.filter(action='support.profile_viewed').exists())
        # Reading staff accounts stays open to every tier.
        self.assertEqual(self.client.get(f'/api/users/accounts/{self.superadmin.id}/').status_code, status.HTTP_200_OK)

    def test_ops_still_manages_counselors_and_its_own_account(self):
        counselor = User.objects.create_user(
            username='tier-managed-counselor', email='tier-managed-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.login(self.ops)
        own = self.client.patch(f'/api/users/accounts/{self.ops.id}/', {'phone': '+998901234567'}, format='json')
        self.assertEqual(own.status_code, status.HTTP_200_OK, own.data)
        deactivated = self.client.post(f'/api/users/accounts/{counselor.id}/deactivate/')
        self.assertEqual(deactivated.status_code, status.HTTP_200_OK, deactivated.data)
        counselor.refresh_from_db()
        self.assertFalse(counselor.is_active)

    def test_superadmin_deactivates_a_lower_tier_admin(self):
        self.login(self.superadmin)
        response = self.client.post(f'/api/users/accounts/{self.ops.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.ops.refresh_from_db()
        self.assertFalse(self.ops.is_active)
        self.assertEqual(
            ProductAuditEvent.objects.filter(action='account.deactivated', target_id=str(self.ops.id)).count(), 1,
        )

    def test_support_answers_tickets_and_ops_deactivates_students(self):
        ticket = SupportTicket.objects.create(
            requester=self.student, category=SupportTicket.Category.TECHNICAL, subject='Cannot sign in',
            message='The login page keeps reloading.',
        )
        self.login(self.support)
        answered = self.client.patch(
            f'/api/support-tickets/{ticket.id}/', {'status': 'resolved', 'admin_response': 'Your login was reset.'},
            format='json',
        )
        self.assertEqual(answered.status_code, status.HTTP_200_OK, answered.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.responded_by, self.support)
        self.assertEqual(ticket.status, SupportTicket.Status.RESOLVED)
        denied = self.client.delete(f'/api/students/{self.profile.id}/')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied.data['code'], 'staff_tier_forbidden')

        self.login(self.ops)
        removed = self.client.delete(f'/api/students/{self.profile.id}/')
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(ProductAuditEvent.objects.filter(action='student.deactivated').count(), 1)

    def test_every_tier_writes_its_own_activity_and_settings(self):
        for user in (self.support, self.ops):
            self.login(user)
            tracked = self.client.post('/api/screen-time/track/', {'entries': [{'page': 'admin_dashboard', 'seconds': 30}]}, format='json')
            self.assertNotEqual(tracked.status_code, status.HTTP_403_FORBIDDEN, (user.username, tracked.data))
            layout = self.client.put('/api/users/accounts/me/dashboard-layout/', {'layout': {}}, format='json')
            self.assertNotEqual(layout.status_code, status.HTTP_403_FORBIDDEN, (user.username, layout.data))
            email = self.client.post('/api/users/accounts/me/email/', {'email': f'{user.username}-new@example.com', 'current_password': 'StrongPass123!'}, format='json')
            self.assertNotEqual(email.status_code, status.HTTP_403_FORBIDDEN, (user.username, email.data))
            # Someone else's account is still out of reach.
            other = self.client.patch(f'/api/users/accounts/{self.superadmin.id}/', {'first_name': 'X'}, format='json')
            self.assertEqual(other.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_staff_tier_rewrites_the_requesters_question(self):
        ticket = SupportTicket.objects.create(
            requester=self.student, category=SupportTicket.Category.TECHNICAL, subject='Cannot sign in',
            message='The login page keeps reloading.',
        )
        for user in (self.support, self.ops, self.superadmin):
            self.login(user)
            for field, value in (('subject', 'Edited'), ('message', 'Edited text'), ('category', 'billing')):
                response = self.client.patch(
                    f'/api/support-tickets/{ticket.id}/', {field: value, 'reply': 'Answer'}, format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, (user.username, field))
                self.assertEqual(response.data[field][0].code, 'ticket_question_read_only')
        ticket.refresh_from_db()
        self.assertEqual(
            (ticket.subject, ticket.message, ticket.category, ticket.replies.count()),
            ('Cannot sign in', 'The login page keeps reloading.', 'technical', 0),
        )
        self.login(self.support)
        unchanged = self.client.patch(
            f'/api/support-tickets/{ticket.id}/',
            {'subject': 'Cannot sign in', 'status': 'in_progress', 'reply': 'Looking into it.'}, format='json',
        )
        self.assertEqual(unchanged.status_code, status.HTTP_200_OK, unchanged.data)
        self.assertEqual(ProductAuditEvent.objects.filter(action='support_ticket.responded').count(), 1)

    def test_a_new_admin_grant_starts_at_the_support_tier(self):
        teacher = User.objects.create_user(
            username='tier-teacher', email='tier-teacher@example.com', password='StrongPass123!',
            role=User.Role.TEACHER, school=self.school,
        )
        self.client.force_authenticate(self.superadmin)
        granted = self.client.patch(f'/api/users/accounts/{teacher.id}/', {'role': 'admin'}, format='json')
        self.assertEqual(granted.status_code, status.HTTP_200_OK, granted.data)
        teacher.refresh_from_db()
        self.assertEqual((teacher.role, teacher.admin_tier), (User.Role.ADMIN, User.AdminTier.SUPPORT))
        change = ProductAuditEvent.objects.get(action='staff.tier_changed')
        self.assertEqual(change.metadata, {'changes': {'admin_tier': {'from': '', 'to': 'support'}}})
        updated = ProductAuditEvent.objects.get(action='account.updated')
        self.assertEqual(updated.metadata['changes'], {'role': {'from': 'teacher', 'to': 'admin'}})

    def test_a_tier_change_is_one_staff_tier_changed_row(self):
        self.client.force_authenticate(self.superadmin)
        changed = self.client.patch(f'/api/users/accounts/{self.support.id}/', {'admin_tier': 'ops'}, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK, changed.data)
        self.assertEqual(
            list(ProductAuditEvent.objects.values_list('action', 'metadata')),
            [('staff.tier_changed', {'changes': {'admin_tier': {'from': 'support', 'to': 'ops'}}})],
        )

    def test_superadmin_adds_staff_with_a_one_time_password(self):
        self.login(self.superadmin)
        payload = {'username': 'new-staff', 'email': 'new-staff@example.com', 'first_name': 'New'}
        created = self.client.post('/api/users/accounts/create-staff/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        staff = User.objects.get(username='new-staff')
        self.assertEqual((staff.role, staff.admin_tier), (User.Role.ADMIN, User.AdminTier.SUPPORT))
        self.assertTrue(staff.must_change_password)
        self.assertTrue(staff.check_password(created.data['temporary_password']))
        self.assertEqual(ProductAuditEvent.objects.get(action='staff.created').metadata, {'staff_tier': 'support'})
        ops = self.client.post('/api/users/accounts/create-staff/', {
            **payload, 'username': 'new-ops', 'email': 'new-ops@example.com', 'admin_tier': 'ops',
        }, format='json')
        self.assertEqual(ops.data['user']['staff_tier'], 'ops')

    def test_only_superadmins_add_staff(self):
        payload = {'username': 'sneaky-staff', 'email': 'sneaky-staff@example.com', 'first_name': 'Sneaky'}
        for actor in (self.ops, self.support):
            self.login(actor)
            response = self.client.post('/api/users/accounts/create-staff/', payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, actor.username)
            self.assertEqual(response.data['code'], 'staff_tier_forbidden')
        self.assertFalse(User.objects.filter(username='sneaky-staff').exists())

    def test_non_staff_are_unaffected_by_tier_routes(self):
        counselor = User.objects.create_user(
            username='plain-counselor', email='plain-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.profile.assigned_counselor = counselor
        self.profile.save(update_fields=['assigned_counselor'])
        self.login(counselor)
        response = self.client.post('/api/tasks/', {
            'title': 'Counselor task', 'student': self.profile.id,
        }, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SuperuserConsistencyTests(APITestCase):
    def test_createsuperuser_produces_a_product_admin(self):
        call_command(
            'createsuperuser', interactive=False, username='root', email='root@example.com', verbosity=0,
        )
        root = User.objects.get(username='root')
        self.assertEqual(root.role, User.Role.ADMIN)
        self.assertEqual(root.admin_tier, User.AdminTier.SUPERADMIN)
        self.assertTrue(root.is_product_admin)
        self.assertFalse(StudentProfile.objects.filter(user=root).exists())

    def test_me_exposes_superuser_and_tier_for_navigation(self):
        root = User.objects.create_superuser('root2', 'root2@example.com', 'StrongPass123!')
        self.client.force_authenticate(root)
        me = self.client.get('/api/users/accounts/me/').data
        self.assertTrue(me['is_superuser'])
        self.assertEqual(me['role'], User.Role.ADMIN)
        self.assertEqual(me['staff_tier'], User.AdminTier.SUPERADMIN)

    def test_superuser_with_another_role_is_still_superadmin(self):
        root = User.objects.create_superuser(
            'root3', 'root3@example.com', 'StrongPass123!', role=User.Role.STUDENT,
        )
        self.assertEqual(root.staff_tier, User.AdminTier.SUPERADMIN)
        self.assertTrue(root.is_product_admin)
