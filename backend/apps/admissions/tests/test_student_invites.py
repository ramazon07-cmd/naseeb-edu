"""Students joining by personal invite or magic link, and the counselor's confirmation queue."""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users import entitlements
from apps.users.models import User

from ..invites import hash_token
from ..models import School, StudentInvite, StudentProfile

PASSWORD = 'Correct-Horse-91'


# Self-join is off by default; these tests cover the switched-on flow.
@override_settings(STUDENT_SELF_JOIN_ENABLED=True)
class InviteBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school = School.objects.create(name='North School', code='north')
        self.other_school = School.objects.create(name='South School', code='south')
        self.counselor = User.objects.create_user(
            'nora', 'nora@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.school,
            first_name='Nora', last_name='Karimova',
        )
        self.colleague = User.objects.create_user(
            'colin', 'colin@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.school,
        )
        self.outsider = User.objects.create_user(
            'oscar', 'oscar@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.other_school,
        )
        self.organization = User.objects.create_user(
            'north-admin', 'org@example.com', PASSWORD, role=User.Role.ORGANIZATION, school=self.school,
        )

    def create_invite(self, user=None, **data):
        self.client.force_authenticate(user or self.counselor)
        payload = {'kind': 'personal', 'first_name': 'Aziz', 'last_name': 'Rahimov', 'email': 'Aziz@Example.com', 'grade': '11', **data}
        response = self.client.post('/api/student-invites/', payload, format='json')
        self.client.force_authenticate(None)
        return response

    def create_link(self, user=None, **data):
        return self.create_invite(user, kind='link', **data)

    def accept(self, token, **data):
        payload = {'username': 'aziz', 'password': PASSWORD, 'email': 'aziz@example.com', **data}
        return self.client.post(f'/api/public/invites/{token}/accept/', payload, format='json')

    def join(self, token=None, **data):
        token = token or self.create_link().data['token']
        response = self.accept(token, first_name='Lola', last_name='Usmonova', **data)
        self.assertEqual(response.status_code, 201, response.data)
        return StudentProfile.objects.get(user__username=data.get('username', 'aziz'))

    def sign_in(self, username='aziz', password=PASSWORD):
        response = self.client.post('/api/auth/token/', {'username': username, 'password': password}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response


class InviteCreationTests(InviteBase):
    def test_personal_invite_returns_token_once_and_stores_only_its_hash(self):
        response = self.create_invite()
        self.assertEqual(response.status_code, 201, response.data)
        token = response.data['token']
        self.assertGreaterEqual(len(token), 43)
        self.assertEqual(response.data['path'], f'/join/{token}')
        self.assertFalse(response.data['emailed'])
        invite = StudentInvite.objects.get()
        self.assertEqual(invite.token_hash, hash_token(token))
        self.assertNotIn(token, str(StudentInvite.objects.values().get()))
        self.assertEqual((invite.email, invite.max_uses, invite.school, invite.counselor), ('aziz@example.com', 1, self.school, self.counselor))
        self.client.force_authenticate(self.counselor)
        listed = self.client.get('/api/student-invites/').data
        self.assertNotIn('token', listed[0])

    def test_personal_invite_needs_name_and_email(self):
        response = self.create_invite(first_name='', email='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_magic_link_defaults_to_one_day_and_caps_at_seven(self):
        before = timezone.now()
        response = self.create_link()
        invite = StudentInvite.objects.get(pk=response.data['id'])
        self.assertIsNone(invite.max_uses)
        self.assertAlmostEqual((invite.expires_at - before).total_seconds(), 86400, delta=60)
        self.assertEqual(self.create_link(expires_in_hours=24 * 8).status_code, 400)
        week = self.create_link(expires_in_hours=24 * 7)
        self.assertEqual(week.status_code, 201)

    def test_students_and_teachers_cannot_invite(self):
        teacher = User.objects.create_user('tina', 'tina@example.com', PASSWORD, role=User.Role.TEACHER, school=self.school)
        self.assertEqual(self.create_invite(teacher).status_code, 403)

    def test_organization_invites_for_a_counselor_of_its_own_school_only(self):
        self.assertEqual(self.create_link(self.organization).status_code, 400)
        self.assertEqual(self.create_link(self.organization, counselor=self.outsider.pk).status_code, 400)
        response = self.create_link(self.organization, counselor=self.colleague.pk)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StudentInvite.objects.get().counselor, self.colleague)

    def test_a_counselor_cannot_invite_for_another_counselor(self):
        response = self.create_link(counselor=self.outsider.pk)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StudentInvite.objects.get().counselor, self.counselor)

    def test_personal_invite_to_an_existing_account_is_refused(self):
        response = self.create_invite(email='NORA@example.com')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.assertFalse(StudentInvite.objects.exists())

    def test_new_personal_invite_replaces_unused_one_for_the_same_email(self):
        first = self.create_invite().data['token']
        self.create_invite()
        self.assertEqual(self.client.get(f'/api/public/invites/{first}/').status_code, 404)


class InviteTenancyTests(InviteBase):
    def test_other_counselors_cannot_list_or_revoke(self):
        invite_id = self.create_link().data['id']
        for user in (self.colleague, self.outsider):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/student-invites/').data, [])
            self.assertEqual(self.client.post(f'/api/student-invites/{invite_id}/revoke/').status_code, 404)
        self.assertIsNone(StudentInvite.objects.get().revoked_at)
        self.client.force_authenticate(self.organization)
        self.assertEqual([row['id'] for row in self.client.get('/api/student-invites/').data], [invite_id])

    def test_other_counselors_cannot_see_confirm_or_reject_pending_students(self):
        profile = self.join()
        for user in (self.colleague, self.outsider):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/pending-students/').data, [])
            self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/confirm/').status_code, 404)
            self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/reject/').status_code, 404)
        profile.refresh_from_db()
        self.assertTrue(profile.awaiting_confirmation)
        outside_org = User.objects.create_user('south-admin', 'so@example.com', PASSWORD, role=User.Role.ORGANIZATION, school=self.other_school)
        self.client.force_authenticate(outside_org)
        self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/confirm/').status_code, 404)


class PublicInviteTests(InviteBase):
    def test_personal_invite_info_prefills_the_student(self):
        token = self.create_invite().data['token']
        data = self.client.get(f'/api/public/invites/{token}/').data
        self.assertEqual(data['school']['name'], 'North School')
        self.assertEqual(data['counselor']['name'], 'Nora Karimova')
        self.assertEqual(data['student']['email'], 'aziz@example.com')
        self.assertEqual(data['student']['grade'], '11')

    def test_magic_link_info_shows_only_school_and_counselor(self):
        token = self.create_link().data['token']
        data = self.client.get(f'/api/public/invites/{token}/').data
        self.assertEqual(set(data), {'kind', 'school', 'counselor', 'expires_at'})
        self.assertNotIn('email', str(data))

    def test_unusable_tokens_share_one_generic_error(self):
        expired = self.create_link().data['token']
        StudentInvite.objects.filter(token_hash=hash_token(expired)).update(expires_at=timezone.now() - timedelta(seconds=1))
        revoked = self.create_link().data
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f"/api/student-invites/{revoked['id']}/revoke/").data['status'], 'revoked')
        self.client.force_authenticate(None)
        used = self.create_invite(email='used@example.com').data['token']
        self.assertEqual(self.accept(used, email='used@example.com').status_code, 201)
        bodies = set()
        for token in (expired, revoked['token'], used, 'not-a-real-token', 'x' * 500):
            for response in (self.client.get(f'/api/public/invites/{token}/'), self.accept(token, username='other', email='o@example.com')):
                self.assertEqual(response.status_code, 404, token)
                bodies.add((response.data['code'], str(response.data['detail'])))
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies.pop()[0], 'invite_unavailable')

    def test_invite_of_a_deactivated_counselor_or_school_is_unavailable(self):
        token = self.create_link().data['token']
        User.objects.filter(pk=self.counselor.pk).update(is_active=False)
        self.assertEqual(self.client.get(f'/api/public/invites/{token}/').status_code, 404)
        User.objects.filter(pk=self.counselor.pk).update(is_active=True)
        School.objects.filter(pk=self.school.pk).update(is_active=False)
        self.assertEqual(self.client.get(f'/api/public/invites/{token}/').status_code, 404)

    def test_accept_creates_a_pending_student_of_that_school_and_counselor(self):
        token = self.create_invite().data['token']
        response = self.accept(token, username='aziz.r', first_name='Azizbek')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'pending')
        user = User.objects.get(username='aziz.r')
        self.assertEqual((user.role, user.school, user.email, user.first_name, user.last_name), (User.Role.STUDENT, self.school, 'aziz@example.com', 'Azizbek', 'Rahimov'))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.must_change_password)
        profile = user.student_profile
        self.assertEqual((profile.school, profile.assigned_counselor, profile.grade), (self.school, self.counselor, '11'))
        self.assertTrue(profile.awaiting_confirmation)
        self.assertEqual(StudentInvite.objects.get().use_count, 1)

    def test_grade_left_not_set_is_stored_empty_not_the_model_default(self):
        profile = self.join(self.create_link(grade='').data['token'])
        profile.refresh_from_db()
        self.assertEqual(profile.grade, '')
        self.client.force_authenticate(self.counselor)
        self.assertEqual([row['grade'] for row in self.client.get('/api/pending-students/').data], [''])

    def test_personal_invite_email_must_match(self):
        token = self.create_invite().data['token']
        response = self.accept(token, email='someone@example.com')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.assertEqual(self.accept(token, email='AZIZ@example.com').status_code, 201)

    def test_username_and_email_must_be_free(self):
        token = self.create_link().data['token']
        taken = self.accept(token, username='NORA', first_name='A', last_name='B')
        self.assertEqual(taken.status_code, 400)
        self.assertIn('username', taken.data)
        used_email = self.accept(token, email='nora@example.com', first_name='A', last_name='B')
        self.assertIn('email', used_email.data)
        bad_name = self.accept(token, username='has space', first_name='A', last_name='B')
        self.assertIn('username', bad_name.data)

    def test_password_validators_apply(self):
        token = self.create_link().data['token']
        for password in ('short', '12345678901', 'password123', 'Lola.Usmonova'):
            response = self.accept(token, password=password, first_name='Lola', last_name='Usmonova')
            self.assertEqual(response.status_code, 400, password)
            self.assertIn('password', response.data)
        self.assertFalse(User.objects.filter(username='aziz').exists())
        self.assertEqual(StudentInvite.objects.get().use_count, 0)

    def test_magic_link_admits_many_students(self):
        token = self.create_link().data['token']
        for n in range(3):
            self.join(token, username=f'kid{n}', email=f'kid{n}@example.com')
        self.assertEqual(StudentInvite.objects.get().use_count, 3)
        self.assertEqual(StudentProfile.objects.filter(awaiting_confirmation=True, assigned_counselor=self.counselor).count(), 3)

    def test_single_use_invite_is_claimed_once_even_after_a_stale_read(self):
        token = self.create_invite().data['token']
        invite = StudentInvite.objects.get()
        stale = StudentInvite.objects.select_related('school', 'counselor').get(pk=invite.pk)
        # A concurrent accept claims the invite after this request read it.
        StudentInvite.objects.filter(pk=invite.pk).update(use_count=1)
        with mock.patch('apps.admissions.invites.find_invite', return_value=stale):
            response = self.accept(token)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['code'], 'invite_unavailable')
        self.assertFalse(User.objects.filter(role=User.Role.STUDENT).exists())
        self.assertEqual(StudentInvite.objects.get().use_count, 1)

    def test_accept_locks_the_invite_row(self):
        token = self.create_invite().data['token']
        from django.db.models import QuerySet

        real = QuerySet.select_for_update
        locked = []

        def spy(queryset, *args, **kwargs):
            locked.append(queryset.model.__name__)
            return real(queryset, *args, **kwargs)

        with mock.patch.object(QuerySet, 'select_for_update', spy):
            self.assertEqual(self.accept(token).status_code, 201)
        self.assertIn('StudentInvite', locked)
        self.assertIn('School', locked)

    def test_pending_students_take_no_seat_and_confirming_checks_the_limit(self):
        subscription = entitlements.ensure_subscription(self.school)
        subscription.plan.max_students = 1
        subscription.plan.save()
        token = self.create_link().data['token']
        first = self.join(token)
        second = self.join(token, username='late', email='late@example.com')
        self.assertEqual(entitlements.seat_queryset(self.school.pk, 'max_students').count(), 0)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/pending-students/{first.pk}/confirm/').status_code, 200)
        full = self.client.post(f'/api/pending-students/{second.pk}/confirm/')
        self.assertEqual(full.status_code, 400)
        self.assertEqual(full.data['code'], 'school_full')
        second.refresh_from_db()
        self.assertTrue(second.awaiting_confirmation)
        self.assertEqual(len(self.client.get('/api/pending-students/').data), 1)

    @override_settings(MAX_PENDING_STUDENTS_PER_SCHOOL=2)
    def test_pending_students_per_school_are_capped(self):
        token = self.create_link().data['token']
        self.join(token, username='kid0', email='kid0@example.com')
        self.join(self.create_link(self.organization, counselor=self.colleague.pk).data['token'], username='kid1', email='kid1@example.com')
        response = self.accept(token, username='kid2', email='kid2@example.com', first_name='A', last_name='B')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invite_paused')
        self.assertFalse(User.objects.filter(username='kid2').exists())
        self.client.force_authenticate(self.counselor)
        kid0 = StudentProfile.objects.get(user__username='kid0')
        self.client.post(f'/api/pending-students/{kid0.pk}/confirm/')
        self.client.force_authenticate(None)
        self.assertEqual(self.accept(token, username='kid2', email='kid2@example.com', first_name='A', last_name='B').status_code, 201)

    def test_read_only_workspace_takes_no_joins(self):
        subscription = entitlements.ensure_subscription(self.school)
        token = self.create_link().data['token']
        subscription.status = subscription.Status.SUSPENDED
        subscription.save()
        response = self.accept(token, first_name='A', last_name='B')
        self.assertEqual(response.data['code'], 'invite_paused')

    def test_page_views_are_throttled_per_ip(self):
        token = self.create_link().data['token']
        rates = {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], 'invite_public': '3/minute'}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': rates}):
            codes = [self.client.get(f'/api/public/invites/{token}/').status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def throttled(self, **overrides):
        rates = {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], **overrides}
        return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': rates})

    def test_only_successful_accepts_count_against_the_ip_sign_up_rate(self):
        token = self.create_link().data['token']
        with self.throttled(invite_accept='2/minute'):
            # A class mistyping passwords behind one address is not locked out ...
            for n in range(5):
                self.assertEqual(self.accept(token, username=f'kid{n}', password='short', first_name='A', last_name='B').status_code, 400)
            self.join(token, username='kid0', email='kid0@example.com')
            self.join(token, username='kid1', email='kid1@example.com')
            # ... but sign-ups themselves are limited.
            response = self.accept(token, username='kid2', email='kid2@example.com', first_name='A', last_name='B')
        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.filter(username='kid2').exists())

    def test_every_attempt_counts_per_ip_and_per_token(self):
        token = self.create_link().data['token']
        with self.throttled(invite_attempt='3/minute'):
            codes = [self.accept('nope', username=f'u{n}').status_code for n in range(4)]
        self.assertEqual(codes, [404, 404, 404, 429])
        cache.clear()
        with self.throttled(invite_token='2/minute'):
            codes = [self.accept(token, password='short', first_name='A', last_name='B').status_code for _ in range(3)]
            # Another token still has its own allowance.
            other = self.accept('another-token', first_name='A', last_name='B').status_code
        self.assertEqual(codes, [400, 400, 429])
        self.assertEqual(other, 404)

    def test_full_width_username_is_the_same_as_its_plain_form(self):
        token = self.create_link().data['token']
        response = self.accept(token, username='ｎｏｒａ', first_name='A', last_name='B')
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)
        created = self.accept(token, username='ａｚｉｚ', first_name='A', last_name='B')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['username'], 'aziz')


class PendingStudentTests(InviteBase):
    def test_pending_student_signs_in_but_reaches_only_me(self):
        profile = self.join()
        self.sign_in()
        me = self.client.get('/api/users/accounts/me/')
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.data['awaiting_confirmation'])
        self.assertEqual(me.data['pending_join'], {'school_name': 'North School', 'counselor_name': 'Nora Karimova'})
        self.assertIsNone(me.data['workspace'])
        for method, path in (
            ('get', '/api/students/'), ('get', f'/api/students/{profile.pk}/'), ('get', '/api/students/onboarding/'),
            ('get', '/api/tasks/'), ('get', '/api/dashboard/stats/'), ('get', '/api/message-channels/'),
            ('get', '/api/notifications/'), ('get', '/api/universities/'), ('get', '/api/student-team/'),
            ('post', '/api/students/onboarding/'), ('patch', '/api/users/accounts/me/'),
            ('post', '/api/users/accounts/me/password/'), ('get', '/api/pending-students/'),
        ):
            response = getattr(self.client, method)(path, {}, format='json')
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.data['code'], 'awaiting_confirmation', path)

    def test_pending_students_stay_out_of_counselor_lists_and_stats_until_confirmed(self):
        profile = self.join()
        self.client.force_authenticate(self.counselor)
        stats = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(stats['students_total'], 0)
        self.assertEqual(stats['badges']['students_pending'], 1)
        rows = self.client.get('/api/students/').data
        self.assertEqual(rows['results'] if isinstance(rows, dict) else rows, [])
        self.assertEqual(self.client.get(f'/api/students/{profile.pk}/').status_code, 404)
        pending = self.client.get('/api/pending-students/').data
        self.assertEqual([(row['id'], row['email'], row['invite']['kind']) for row in pending], [(profile.pk, 'aziz@example.com', 'link')])

        self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/confirm/').status_code, 200)
        stats = self.client.get('/api/dashboard/stats/').data
        self.assertEqual((stats['students_total'], stats['badges']['students_pending']), (1, 0))
        self.assertEqual(self.client.get(f'/api/students/{profile.pk}/').status_code, 200)
        self.assertEqual(self.client.get('/api/pending-students/').data, [])

    def test_confirmed_student_reaches_the_workspace(self):
        profile = self.join()
        self.client.force_authenticate(self.counselor)
        self.client.post(f'/api/pending-students/{profile.pk}/confirm/')
        self.client.force_authenticate(None)
        self.sign_in()
        self.assertFalse(self.client.get('/api/users/accounts/me/').data['awaiting_confirmation'])
        self.assertEqual(self.client.get('/api/students/onboarding/').status_code, 200)

    def test_rejected_student_is_removed_and_cannot_sign_in(self):
        profile = self.join()
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/pending-students/{profile.pk}/reject/')
        self.assertEqual(response.data['status'], 'rejected')
        self.assertFalse(User.objects.filter(username='aziz').exists())
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/token/', {'username': 'aziz', 'password': PASSWORD}, format='json')
        self.assertEqual(login.status_code, 401)
        # The email and username are free again.
        self.join(username='aziz')

    def test_reject_after_a_concurrent_confirm_reports_it(self):
        profile = self.join()
        from ..views.invites import PendingStudentViewSet

        self.client.force_authenticate(self.counselor)
        self.client.post(f'/api/pending-students/{profile.pk}/confirm/')
        # The reject request found the student still pending, then lost the race.
        with mock.patch.object(PendingStudentViewSet, 'get_object', return_value=profile):
            response = self.client.post(f'/api/pending-students/{profile.pk}/reject/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual((response.data['status'], response.data['code']), ('confirmed', 'already_confirmed'))
        self.assertTrue(User.objects.filter(username='aziz', is_active=True).exists())

    def test_acting_on_an_already_confirmed_student_reports_it(self):
        profile = self.join()
        self.client.force_authenticate(self.counselor)
        self.client.post(f'/api/pending-students/{profile.pk}/confirm/')
        # A second tab (or the school account) acts after the confirm.
        reject = self.client.post(f'/api/pending-students/{profile.pk}/reject/')
        self.assertEqual((reject.status_code, reject.data['status']), (409, 'confirmed'))
        confirm = self.client.post(f'/api/pending-students/{profile.pk}/confirm/')
        self.assertEqual((confirm.status_code, confirm.data['status']), (200, 'confirmed'))
        self.assertTrue(User.objects.filter(username='aziz', is_active=True).exists())
        # Confirming is not a check-in with the student.
        from ..counselor_summary import NOT_A_CHECK_IN
        self.assertTrue(any('Student confirmed: x'.startswith(prefix) for prefix in NOT_A_CHECK_IN))

    def test_reject_reports_the_real_outcome(self):
        profile = self.join()
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/pending-students/{profile.pk}/reject/')
        self.assertEqual((response.data['status'], response.data['outcome']), ('rejected', 'deleted'))

    def test_organization_lists_its_counselors_and_sees_the_pending_badge(self):
        self.join()
        self.client.force_authenticate(self.organization)
        names = {row['id'] for row in self.client.get('/api/student-invites/counselors/').data}
        self.assertEqual(names, {self.counselor.pk, self.colleague.pk})
        self.assertEqual(self.client.get('/api/dashboard/stats/').data['badges']['students_pending'], 1)
        self.client.force_authenticate(self.counselor)
        self.assertEqual([row['id'] for row in self.client.get('/api/student-invites/counselors/').data], [self.counselor.pk])

    def test_rejected_session_ends(self):
        profile = self.join()
        self.sign_in()
        self.client.force_authenticate(self.counselor)
        self.client.post(f'/api/pending-students/{profile.pk}/reject/')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, 401)

    def test_organization_confirms_students_of_its_school(self):
        profile = self.join()
        self.client.force_authenticate(self.organization)
        self.assertEqual(len(self.client.get('/api/pending-students/').data), 1)
        self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/confirm/').status_code, 200)
        profile.refresh_from_db()
        self.assertFalse(profile.awaiting_confirmation)


class SelfJoinDisabledTests(InviteBase):
    """Off (the default): only staff create student accounts; invite links stop working."""

    def test_me_reports_the_switch(self):
        self.client.force_authenticate(self.counselor)
        self.assertTrue(self.client.get('/api/users/accounts/me/').data['student_self_join'])
        with override_settings(STUDENT_SELF_JOIN_ENABLED=False):
            self.assertFalse(self.client.get('/api/users/accounts/me/').data['student_self_join'])

    def test_counselor_and_organization_cannot_create_invites(self):
        with override_settings(STUDENT_SELF_JOIN_ENABLED=False):
            for user, extra in ((self.counselor, {}), (self.organization, {'counselor': self.counselor.pk})):
                for kind in ('personal', 'link'):
                    response = self.create_invite(user, kind=kind, **extra)
                    self.assertEqual(response.status_code, 403, (user.username, kind))
                    self.assertEqual(response.data['code'], 'self_join_disabled')
        self.assertFalse(StudentInvite.objects.exists())

    def test_refusal_is_localized(self):
        self.client.force_authenticate(self.counselor)
        with override_settings(STUDENT_SELF_JOIN_ENABLED=False):
            response = self.client.post('/api/student-invites/', {'kind': 'link'}, format='json', HTTP_ACCEPT_LANGUAGE='uz')
        self.assertIn('maslahatchisidan', response.data['detail'])

    def test_existing_links_stop_admitting_students(self):
        token = self.create_link().data['token']
        with override_settings(STUDENT_SELF_JOIN_ENABLED=False):
            info = self.client.get(f'/api/public/invites/{token}/')
            self.assertEqual((info.status_code, info.data['code']), (404, 'invite_unavailable'))
            accepted = self.accept(token, first_name='Lola', last_name='Usmonova')
            self.assertEqual((accepted.status_code, accepted.data['code']), (404, 'invite_unavailable'))
        self.assertFalse(User.objects.filter(username='aziz').exists())
        self.assertEqual(StudentInvite.objects.get().use_count, 0)

    def test_students_already_waiting_can_still_be_confirmed(self):
        profile = self.join()
        with override_settings(STUDENT_SELF_JOIN_ENABLED=False):
            self.client.force_authenticate(self.counselor)
            self.assertEqual(self.client.post(f'/api/pending-students/{profile.pk}/confirm/').status_code, 200)
        profile.refresh_from_db()
        self.assertFalse(profile.awaiting_confirmation)


class InviteLocalizationTests(InviteBase):
    def test_generic_error_is_localized(self):
        response = self.client.get('/api/public/invites/unknown/', HTTP_ACCEPT_LANGUAGE='ru')
        self.assertEqual(response.data['code'], 'invite_unavailable')
        self.assertIn('приглашение', response.data['detail'])
