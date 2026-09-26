import threading
from datetime import timedelta
from importlib import import_module
from unittest import skipUnless

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import Essay, ParentStudentLink, School, StudentProfile
from apps.users import entitlements
from apps.users.auth_views import token_pair_for_user
from apps.users.models import PLAN_FEATURES, Plan, ProductAuditEvent, User, WorkspaceSubscription


def use_plan(school, code='custom', **fields):
    values = {
        'name': code.title(),
        'max_counselors': None,
        'max_students': None,
        'max_teachers': None,
        'features': {key: True for key in PLAN_FEATURES},
        **fields,
    }
    plan, _ = Plan.objects.update_or_create(code=code, defaults=values)
    WorkspaceSubscription.objects.filter(school=school).update(plan=plan)
    return plan


def make_user(username, role, school, **extra):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='StrongPass123!',
        role=role,
        school=school,
        **extra,
    )


class PlanDefaultsTests(APITestCase):
    def test_new_workspaces_start_on_the_plan_matching_their_type(self):
        school = School.objects.create(name='Plan School', code='plan-school')
        individual = School.objects.create(
            name='Solo Workspace', code='solo', workspace_type=School.WorkspaceType.INDIVIDUAL,
        )
        self.assertEqual(school.subscription.plan.code, entitlements.SCHOOL_STANDARD)
        self.assertEqual(school.subscription.plan.max_counselors, 3)
        self.assertEqual(school.subscription.status, WorkspaceSubscription.Status.ACTIVE)
        self.assertEqual(individual.subscription.plan.code, entitlements.INDIVIDUAL_COUNSELOR)
        self.assertEqual(individual.subscription.plan.max_counselors, 1)
        self.assertEqual(individual.subscription.plan.max_teachers, 0)
        self.assertTrue(Plan.objects.filter(code=entitlements.CENTER).exists())

    def test_seed_migration_backfills_existing_workspaces(self):
        school = School.objects.create(name='Legacy School', code='legacy')
        individual = School.objects.create(
            name='Legacy Solo', code='legacy-solo', workspace_type=School.WorkspaceType.INDIVIDUAL,
        )
        WorkspaceSubscription.objects.filter(school__in=[school, individual]).delete()
        seed = import_module('apps.users.migrations.0010_admin_seed_plans').seed
        seed(django_apps, None)
        seed(django_apps, None)  # idempotent
        self.assertEqual(WorkspaceSubscription.objects.get(school=school).plan.code, entitlements.SCHOOL_STANDARD)
        self.assertEqual(
            WorkspaceSubscription.objects.get(school=individual).plan.code, entitlements.INDIVIDUAL_COUNSELOR,
        )
        self.assertEqual(WorkspaceSubscription.objects.filter(school=school).count(), 1)

    def test_plan_features_follow_the_fixed_schema(self):
        plan = Plan.objects.create(code='partial', name='Partial', features={'ai_assistant': True})
        self.assertEqual(set(plan.features), set(PLAN_FEATURES))
        self.assertFalse(plan.features['essay_coach'])
        with self.assertRaises(ValidationError):
            Plan.objects.create(code='unknown', name='Unknown', features={'teleport': True})
        with self.assertRaises(ValidationError):
            Plan.objects.create(code='stringly', name='Stringly', features={'ai_assistant': 'yes'})


class EntitlementsNeedTransactionTests(SimpleTestCase):
    def test_check_refuses_to_run_without_a_transaction(self):
        with self.assertRaises(RuntimeError):
            entitlements.check(School(pk=1), 'max_students', 1)


class SeatLimitTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Seat School', code='seat-school')
        self.other_school = School.objects.create(name='Other School', code='other-school')
        self.admin = User.objects.create_user(
            username='seat-admin', email='seat-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.counselor = make_user('seat-counselor', User.Role.COUNSELOR, self.school)

    def quick_create(self, name):
        return self.client.post('/api/students/quick-create/', {
            'name': name, 'password': 'StrongPass123!',
        }, format='json')

    def test_counselor_limit_comes_from_the_plan(self):
        use_plan(self.school, max_counselors=1)
        self.client.force_authenticate(self.admin)
        payload = {
            'username': 'second', 'email': 'second@example.com', 'first_name': 'Second',
            'password': 'StrongPass123!', 'school': self.school.id,
        }
        rejected = self.client.post('/api/users/accounts/create-counselor/', payload, format='json')
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('at most 1 active counselors', str(rejected.data))

        use_plan(self.school, code=entitlements.CENTER)
        created = self.client.post('/api/users/accounts/create-counselor/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

    def test_quick_create_stops_at_the_student_seat_limit(self):
        use_plan(self.school, max_students=1)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.quick_create('First Student').status_code, status.HTTP_201_CREATED)
        rejected = self.quick_create('Second Student')
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(rejected.data['code'], 'seat_limit_reached')
        self.assertEqual(User.objects.filter(school=self.school, role=User.Role.STUDENT).count(), 1)

    def test_inactive_students_do_not_hold_a_seat(self):
        use_plan(self.school, max_students=1)
        make_user('former-student', User.Role.STUDENT, self.school, is_active=False)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.quick_create('New Student').status_code, status.HTTP_201_CREATED)

    def test_moving_an_account_checks_the_destination_workspace(self):
        use_plan(self.other_school, code='full', max_students=1)
        make_user('occupant', User.Role.STUDENT, self.other_school)
        mover = make_user('mover', User.Role.STUDENT, self.school)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/users/accounts/{mover.id}/', {'school': self.other_school.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('at most 1 active student accounts', str(response.data))
        mover.refresh_from_db()
        self.assertEqual(mover.school_id, self.school.id)

    def test_reactivation_takes_a_seat_but_plain_edits_do_not(self):
        use_plan(self.school, max_students=1)
        make_user('holder', User.Role.STUDENT, self.school)
        dormant = make_user('dormant', User.Role.STUDENT, self.school, is_active=False)
        self.client.force_authenticate(self.admin)
        reactivate = self.client.patch(f'/api/users/accounts/{dormant.id}/', {'is_active': True}, format='json')
        self.assertEqual(reactivate.status_code, status.HTTP_400_BAD_REQUEST)

        # A downgrade below current usage blocks new seats, not edits.
        make_user('over-limit', User.Role.STUDENT, self.school)
        holder = User.objects.get(username='holder')
        edit = self.client.patch(f'/api/users/accounts/{holder.id}/', {'phone': '+998900000000'}, format='json')
        self.assertEqual(edit.status_code, status.HTTP_200_OK)

    def test_individual_workspace_has_no_teacher_or_organization_seats(self):
        individual = School.objects.create(
            name='Solo', code='solo-seat', workspace_type=School.WorkspaceType.INDIVIDUAL,
        )
        self.client.force_authenticate(self.admin)
        teacher = self.client.post('/api/users/accounts/', {
            'username': 'solo-teacher', 'email': 'solo-teacher@example.com', 'role': User.Role.TEACHER,
            'school': individual.id,
        }, format='json')
        self.assertEqual(teacher.status_code, status.HTTP_400_BAD_REQUEST)
        account = self.client.post(f'/api/schools/{individual.id}/create-account/', {
            'username': 'solo-org', 'email': 'solo-org@example.com', 'password': 'StrongPass123!',
        }, format='json')
        self.assertEqual(account.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(account.data['code'], 'feature_not_in_plan')

    def test_suspended_workspace_takes_no_new_seats(self):
        WorkspaceSubscription.objects.filter(school=self.school).update(
            status=WorkspaceSubscription.Status.SUSPENDED,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/students/quick-create/', {
            'name': 'Blocked Student', 'password': 'StrongPass123!', 'school': self.school.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'workspace_read_only')


class ReadOnlyWorkspaceTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Frozen School', code='frozen-school')
        self.student = make_user('frozen-student', User.Role.STUDENT, self.school)
        StudentProfile.objects.create(user=self.student, school=self.school, school_name=self.school.name)
        self.admin = User.objects.create_user(
            username='frozen-admin', email='frozen-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )

    def login(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_pair_for_user(user)["access"]}')

    def create_task(self):
        return self.client.post('/api/tasks/', {'title': 'Personal goal'}, format='json')

    def set_subscription(self, **fields):
        WorkspaceSubscription.objects.filter(school=self.school).update(**fields)

    def test_suspended_workspace_allows_reads_and_rejects_writes(self):
        self.set_subscription(status=WorkspaceSubscription.Status.SUSPENDED)
        self.login(self.student)
        self.assertEqual(self.client.get('/api/tasks/').status_code, status.HTTP_200_OK)
        response = self.create_task()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'workspace_read_only')

        self.set_subscription(status=WorkspaceSubscription.Status.ACTIVE)
        self.assertNotEqual(self.create_task().status_code, status.HTTP_403_FORBIDDEN)

    def test_a_past_period_end_is_read_only_before_the_status_changes(self):
        self.set_subscription(period_end=timezone.localdate() - timedelta(days=1))
        self.login(self.student)
        self.assertEqual(self.create_task().data['code'], 'workspace_read_only')

    def test_product_staff_are_not_frozen_by_a_workspace(self):
        self.set_subscription(status=WorkspaceSubscription.Status.EXPIRED)
        self.login(self.admin)
        response = self.client.patch(f'/api/users/accounts/{self.student.id}/', {'phone': '+998901112233'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_forced_password_change_still_works_when_read_only(self):
        self.set_subscription(status=WorkspaceSubscription.Status.SUSPENDED)
        self.student.must_change_password = True
        self.student.save(update_fields=['must_change_password'])
        self.login(self.student)
        response = self.client.post('/api/users/accounts/change-password/', {
            'new_password': 'AnotherStrong456!', 'confirm_password': 'AnotherStrong456!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_school_lockout_and_read_only_checks_share_one_user_query(self):
        from rest_framework.test import APIRequestFactory

        from apps.users.authentication import VersionedJWTAuthentication

        self.set_subscription(status=WorkspaceSubscription.Status.SUSPENDED)
        token = token_pair_for_user(self.student)['access']
        request = APIRequestFactory().post('/api/tasks/', {}, HTTP_AUTHORIZATION=f'Bearer {token}')
        with self.assertNumQueries(1):
            with self.assertRaises(Exception) as raised:
                VersionedJWTAuthentication().authenticate(request)
        self.assertEqual(raised.exception.detail['code'], 'workspace_read_only')

        School.objects.filter(pk=self.school.pk).update(is_active=False)
        with self.assertNumQueries(1):
            with self.assertRaises(Exception) as raised:
                VersionedJWTAuthentication().authenticate(request)
        self.assertEqual(raised.exception.detail['code'], 'school_inactive')

    def test_me_reports_the_workspace_plan_and_access(self):
        self.set_subscription(status=WorkspaceSubscription.Status.SUSPENDED)
        self.login(self.student)
        workspace = self.client.get('/api/users/accounts/me/').data['workspace']
        self.assertEqual(workspace['plan'], entitlements.SCHOOL_STANDARD)
        self.assertTrue(workspace['read_only'])
        self.assertTrue(workspace['features']['ai_assistant'])


class FeatureFlagTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Feature School', code='feature-school')
        self.student_user = make_user('feature-student', User.Role.STUDENT, self.school)
        self.student = StudentProfile.objects.create(
            user=self.student_user, school=self.school, school_name=self.school.name,
        )
        features = {key: True for key in PLAN_FEATURES}
        use_plan(self.school, code='no-ai', features={**features, 'ai_assistant': False, 'essay_coach': False})
        self.client.force_authenticate(self.student_user)

    @override_settings(AI_ASSISTANT_ENABLED=True, AI_GATEWAY_API_KEY='')
    def test_assistant_is_gated_by_the_plan(self):
        response = self.client.post(
            '/api/assistant/chat/', {'messages': [{'role': 'user', 'content': 'Hello'}]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'feature_not_in_plan')

    @override_settings(AI_GATEWAY_API_KEY='')
    def test_essay_coach_is_gated_by_the_plan(self):
        essay = Essay.objects.create(student=self.student, title='Draft', prompt='', content='A real paragraph.')
        response = self.client.post(
            f'/api/essay-lab/essays/{essay.pk}/depth-check/', {'base_seq': 0}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'feature_not_in_plan')

        WorkspaceSubscription.objects.filter(school=self.school).update(
            plan=Plan.objects.get(code=entitlements.SCHOOL_STANDARD),
        )
        allowed = self.client.post(
            f'/api/essay-lab/essays/{essay.pk}/depth-check/', {'base_seq': 0}, format='json',
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)


class ParentFeatureFlagTests(APITestCase):
    def setUp(self):
        features = {key: True for key in PLAN_FEATURES}
        self.with_ai = School.objects.create(name='With AI', code='with-ai')
        self.without_ai = School.objects.create(name='Without AI', code='without-ai')
        use_plan(self.with_ai, code='all-in', features=features)
        use_plan(self.without_ai, code='no-ai', features={**features, 'ai_assistant': False})
        self.parent = make_user('flag-parent', User.Role.PARENT, None)

    def link(self, school, status_value=ParentStudentLink.Status.ACTIVE):
        student = make_user(f'flag-child-{school.code}-{status_value}', User.Role.STUDENT, school)
        profile = StudentProfile.objects.create(user=student, school=school, school_name=school.name)
        return ParentStudentLink.objects.create(parent=self.parent, student=profile, status=status_value)

    def enabled(self):
        with self.assertNumQueries(1):
            return entitlements.feature_enabled(self.parent, 'ai_assistant')

    def test_a_parent_without_children_gets_no_plan_features(self):
        self.assertFalse(self.enabled())

    def test_a_parent_follows_the_plans_of_linked_schools(self):
        self.link(self.without_ai)
        self.assertFalse(self.enabled())
        self.assertTrue(entitlements.feature_enabled(self.parent, 'reports'))
        self.link(self.with_ai)
        self.assertTrue(self.enabled())

    def test_only_accepted_links_count(self):
        self.link(self.with_ai, ParentStudentLink.Status.PENDING)
        self.link(self.with_ai, ParentStudentLink.Status.REVOKED)
        self.assertFalse(self.enabled())

    def test_a_school_without_a_subscription_keeps_full_access(self):
        self.link(self.without_ai)
        WorkspaceSubscription.objects.filter(school=self.without_ai).delete()
        self.assertTrue(self.enabled())

    def test_require_feature_refuses_a_parent_outside_the_plan(self):
        from rest_framework.exceptions import PermissionDenied
        from rest_framework.test import APIRequestFactory

        self.link(self.without_ai)
        request = APIRequestFactory().get('/')
        request.user = self.parent
        with self.assertRaises(PermissionDenied):
            entitlements.require_feature(request, 'ai_assistant')

    def test_admins_and_other_schoolless_users_are_unchanged(self):
        admin = make_user('flag-admin', User.Role.ADMIN, None)
        loose_student = make_user('flag-loose', User.Role.STUDENT, None)
        self.parent.is_superuser = True
        with self.assertNumQueries(0):
            self.assertTrue(entitlements.feature_enabled(admin, 'ai_assistant'))
            self.assertTrue(entitlements.feature_enabled(loose_student, 'ai_assistant'))
            self.assertTrue(entitlements.feature_enabled(self.parent, 'ai_assistant'))


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Billing School', code='billing-school')
        self.ops = User.objects.create_user(
            username='ops', email='ops@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.OPS,
        )
        self.support = User.objects.create_user(
            username='support', email='support@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.SUPPORT,
        )
        self.url = f'/api/users/workspace-subscriptions/{self.school.id}/'

    def test_ops_changes_plan_and_status_and_the_change_is_audited(self):
        self.client.force_authenticate(self.ops)
        response = self.client.patch(self.url, {
            'plan': entitlements.CENTER, 'status': 'suspended', 'period_end': '2027-06-30',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['read_only'])
        subscription = WorkspaceSubscription.objects.get(school=self.school)
        self.assertEqual(subscription.plan.code, entitlements.CENTER)
        self.assertEqual(subscription.updated_by, self.ops)
        event = ProductAuditEvent.objects.get(action='subscription.changed')
        self.assertEqual(event.metadata['changes']['plan'], {'from': entitlements.SCHOOL_STANDARD, 'to': entitlements.CENTER})
        self.assertEqual(event.metadata['changes']['status']['to'], 'suspended')

        # Saving the same values again records nothing new.
        self.client.patch(self.url, {'plan': entitlements.CENTER}, format='json')
        self.assertEqual(ProductAuditEvent.objects.filter(action='subscription.changed').count(), 1)

    def test_period_must_not_end_before_it_starts(self):
        self.client.force_authenticate(self.ops)
        response = self.client.patch(self.url, {
            'period_start': '2027-01-01', 'period_end': '2026-01-01',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_support_reads_but_cannot_change_a_subscription(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/users/plans/').status_code, status.HTTP_200_OK)
        response = self.client.patch(self.url, {'status': 'suspended'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_school_accounts_cannot_read_plans_or_subscriptions(self):
        organization = make_user('billing-org', User.Role.ORGANIZATION, self.school)
        self.client.force_authenticate(organization)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/users/plans/').status_code, status.HTTP_403_FORBIDDEN)

    def test_school_list_reports_plan_and_seat_usage_in_constant_queries(self):
        make_user('usage-counselor', User.Role.COUNSELOR, self.school)
        make_user('usage-student', User.Role.STUDENT, self.school)
        make_user('usage-inactive', User.Role.STUDENT, self.school, is_active=False)
        for index in range(5):
            School.objects.create(name=f'Extra {index}', code=f'extra-{index}')
        self.client.force_authenticate(self.ops)
        with self.assertNumQueries(3):
            response = self.client.get('/api/schools/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data['results'] if item['id'] == self.school.id)
        self.assertEqual(row['seat_usage'], {'max_counselors': 1, 'max_students': 1, 'max_teachers': 0})
        self.assertEqual(row['subscription']['plan'], entitlements.SCHOOL_STANDARD)
        self.assertFalse(row['subscription']['read_only'])


@skipUnless(connection.vendor == 'postgresql', 'Row locks need PostgreSQL.')
class ConcurrentSeatTests(TransactionTestCase):
    def test_concurrent_creations_cannot_exceed_the_limit(self):
        school = School.objects.create(name='Race School', code='race-school')
        use_plan(school, code='race', max_students=2)
        workers = 6
        barrier = threading.Barrier(workers)
        outcomes = []

        def create(index):
            try:
                barrier.wait()
                with transaction.atomic():
                    entitlements.check(school, 'max_students', 1)
                    make_user(f'racer-{index}', User.Role.STUDENT, school)
                outcomes.append('created')
            except entitlements.EntitlementError:
                outcomes.append('rejected')
            finally:
                connection.close()

        threads = [threading.Thread(target=create, args=(index,)) for index in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count('created'), 2)
        self.assertEqual(outcomes.count('rejected'), workers - 2)
        self.assertEqual(User.objects.filter(school=school, role=User.Role.STUDENT).count(), 2)


class TenancyServiceSeatTests(APITestCase):
    """Moves, reactivations and creations through the tenancy services respect seats."""

    def setUp(self):
        self.school = School.objects.create(name='Service School', code='service-school')
        self.full = School.objects.create(name='Full School', code='full-school')
        self.admin = User.objects.create_user(
            username='service-admin', email='service-admin@example.com', password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        use_plan(self.full, code='one-student', max_students=1)
        make_user('full-occupant', User.Role.STUDENT, self.full)

    def student(self, username, school, **extra):
        user = make_user(username, User.Role.STUDENT, school, **extra)
        return StudentProfile.objects.create(user=user, school=school, school_name=school.name)

    def test_move_student_checks_the_destination_seats(self):
        from apps.admissions.tenancy import move_student

        profile = self.student('service-mover', self.school)
        with self.assertRaises(entitlements.EntitlementError):
            move_student(profile, self.full, self.admin)
        profile.refresh_from_db()
        self.assertEqual(profile.school, self.school)
        self.assertFalse(ProductAuditEvent.objects.filter(action='student.moved').exists())

    def test_an_inactive_student_moves_without_taking_a_seat(self):
        from apps.admissions.tenancy import move_student

        profile = self.student('service-dormant', self.school, is_active=False)
        move_student(profile, self.full, self.admin)
        profile.refresh_from_db()
        self.assertEqual(profile.school, self.full)

    def test_reactivation_through_the_service_checks_seats(self):
        from apps.admissions.tenancy import set_student_active

        profile = self.student('service-sleeper', self.full, is_active=False)
        with self.assertRaises(entitlements.EntitlementError):
            set_student_active(profile, True, self.admin)
        profile.user.refresh_from_db()
        self.assertFalse(profile.user.is_active)

    def test_create_student_account_checks_seats(self):
        from apps.admissions.tenancy import create_student_account

        with self.assertRaises(entitlements.EntitlementError):
            create_student_account(
                school=self.full, full_name='Over Limit', password='StrongPass123!', created_by=self.admin,
            )
        self.assertFalse(User.objects.filter(first_name='Over').exists())
