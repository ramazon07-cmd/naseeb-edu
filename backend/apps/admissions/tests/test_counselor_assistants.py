"""Counselor assistants: email invitations, accepting, splitting students and the assistant's counselor reach over their own students."""
from datetime import date, timedelta
from unittest.mock import patch
from smtplib import SMTPException

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import ProductAuditEvent, User

from ..assistants import hash_token
from ..models import AssistantInvite, Essay, RoadmapMission, School, StudentProfile, Task

PASSWORD = 'Correct-Horse-91'


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://app.example.com',
)
class AssistantBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school = School.objects.create(name='North School', code='north')
        self.other_school = School.objects.create(name='South School', code='south')
        self.counselor = User.objects.create_user(
            'nora', 'nora@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.school,
            first_name='Nora', last_name='Karimova',
        )
        self.colleague = User.objects.create_user('colin', 'colin@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.school)
        self.teacher = User.objects.create_user('tom', 'tom@example.com', PASSWORD, role=User.Role.TEACHER, school=self.school)
        self.organization = User.objects.create_user('org', 'org@example.com', PASSWORD, role=User.Role.ORGANIZATION, school=self.school)
        self.mine = self.make_student('ali', self.counselor)
        self.also_mine = self.make_student('vali', self.counselor)
        self.colleagues = self.make_student('gani', self.colleague)

    def make_student(self, username, counselor, school=None):
        school = school or self.school
        user = User.objects.create_user(username, f'{username}@example.com', PASSWORD, role=User.Role.STUDENT, school=school)
        return StudentProfile.objects.create(user=user, school=school, school_name=school.name, assigned_counselor=counselor)

    def invite(self, user=None, **data):
        self.client.force_authenticate(user or self.counselor)
        payload = {'first_name': 'Aziza', 'last_name': 'Tosheva', 'email': 'Aziza@Example.com', **data}
        response = self.client.post('/api/assistant-invites/', payload, format='json')
        self.client.force_authenticate(None)
        return response

    def token_of(self, response):
        return response.data['path'].rsplit('/', 1)[1]

    def accept(self, token, **data):
        payload = {'username': 'aziza', 'password': PASSWORD, **data}
        return self.client.post(f'/api/public/assistant-invites/{token}/accept/', payload, format='json')

    def make_assistant(self, counselor=None, username='aziza'):
        counselor = counselor or self.counselor
        return User.objects.create_user(
            username, f'{username}@example.com', PASSWORD, role=User.Role.ASSISTANT,
            school=counselor.school, supervising_counselor=counselor,
        )

    def give(self, assistant, *students, counselor=None):
        self.client.force_authenticate(counselor or self.counselor)
        response = self.client.put(
            f'/api/assistants/{assistant.pk}/students/', {'students': [s.pk for s in students]}, format='json',
        )
        self.client.force_authenticate(None)
        return response


class AssistantInviteTests(AssistantBase):
    def test_counselor_invite_is_emailed_with_a_single_use_link(self):
        response = self.invite()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['emailed'])
        token = self.token_of(response)
        invite = AssistantInvite.objects.get()
        self.assertEqual(invite.token_hash, hash_token(token))
        self.assertEqual(invite.email, 'aziza@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['aziza@example.com'])
        self.assertIn(f'https://app.example.com/assistant-invite/{token}', mail.outbox[0].body)
        self.assertTrue(ProductAuditEvent.objects.filter(action='assistant_invite.created').exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend', DEBUG=False)
    def test_without_mail_the_counselor_gets_the_link_and_nothing_is_printed(self):
        response = self.invite()
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['emailed'])
        self.assertTrue(response.data['path'].startswith('/assistant-invite/'))

    def test_only_counselors_invite_assistants(self):
        assistant = self.make_assistant()
        student = self.mine.user
        for user in (self.teacher, self.organization, student, assistant):
            with self.subTest(role=user.role):
                self.assertEqual(self.invite(user).status_code, 403)
        self.assertFalse(AssistantInvite.objects.exists())

    def test_email_with_an_account_is_refused(self):
        response = self.invite(email='TOM@example.com')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_counselor_lists_and_revokes_only_their_own_invites(self):
        own = self.invite().data
        self.invite(self.colleague, email='other@example.com')
        self.client.force_authenticate(self.counselor)
        listed = self.client.get('/api/assistant-invites/').data['results']
        self.assertEqual([row['id'] for row in listed], [own['id']])
        other = AssistantInvite.objects.get(email='other@example.com')
        self.assertEqual(self.client.post(f'/api/assistant-invites/{other.pk}/revoke/').status_code, 404)
        revoked = self.client.post(f"/api/assistant-invites/{own['id']}/revoke/")
        self.assertEqual(revoked.data['status'], 'revoked')

    def test_mail_failure_keeps_a_shareable_invite(self):
        with patch('apps.admissions.assistants.send_mail', side_effect=SMTPException('offline')):
            response = self.invite()
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['emailed'])
        self.assertEqual(self.client.get(f"/api/public/assistant-invites/{self.token_of(response)}/").status_code, 200)

    def test_invites_are_paginated_without_hiding_older_links(self):
        for i in range(3):
            self.invite(email=f'new{i}@example.com')
        self.client.force_authenticate(self.counselor)
        first = self.client.get('/api/assistant-invites/?page_size=2').data
        second = self.client.get('/api/assistant-invites/?page_size=2&page=2').data
        self.assertEqual(first['count'], 3)
        self.assertTrue(first['next'])
        self.assertEqual(len(first['results']), 2)
        self.assertEqual(len(second['results']), 1)

    def test_reinviting_revokes_the_previous_link(self):
        previous = self.token_of(self.invite())
        latest = self.token_of(self.invite())
        self.assertEqual(self.client.get(f'/api/public/assistant-invites/{previous}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/public/assistant-invites/{latest}/').status_code, 200)


class AssistantAcceptTests(AssistantBase):
    def test_accepting_creates_an_assistant_who_can_sign_in(self):
        token = self.token_of(self.invite())
        info = self.client.get(f'/api/public/assistant-invites/{token}/')
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.data['counselor']['name'], 'Nora Karimova')
        self.assertEqual(info.data['assistant']['email'], 'aziza@example.com')

        response = self.accept(token)
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username='aziza')
        self.assertEqual(user.role, User.Role.ASSISTANT)
        self.assertEqual(user.school, self.school)
        self.assertEqual(user.supervising_counselor, self.counselor)
        self.assertEqual(user.email, 'aziza@example.com')
        self.assertFalse(user.must_change_password)
        login = self.client.post('/api/auth/token/', {'username': 'aziza', 'password': PASSWORD}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(AssistantInvite.objects.get().accepted_user, user)

    def test_a_link_works_once(self):
        token = self.token_of(self.invite())
        self.assertEqual(self.accept(token).status_code, 201)
        self.assertEqual(self.accept(token, username='second').status_code, 404)
        self.assertEqual(self.client.get(f'/api/public/assistant-invites/{token}/').status_code, 404)

    def test_expired_revoked_and_unknown_links_are_all_unavailable(self):
        expired = self.token_of(self.invite())
        AssistantInvite.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        revoked_response = self.invite(email='second@example.com')
        AssistantInvite.objects.filter(pk=revoked_response.data['id']).update(revoked_at=timezone.now())
        for token in (expired, self.token_of(revoked_response), 'not-a-real-token'):
            with self.subTest(token=token[:6]):
                self.assertEqual(self.accept(token).status_code, 404)
        self.assertFalse(User.objects.filter(role=User.Role.ASSISTANT).exists())

    def test_a_deactivated_counselors_link_stops_working(self):
        token = self.token_of(self.invite())
        User.objects.filter(pk=self.counselor.pk).update(is_active=False)
        self.assertEqual(self.accept(token).status_code, 404)

    def test_an_invite_stops_working_after_the_counselor_changes_school(self):
        token = self.token_of(self.invite())
        User.objects.filter(pk=self.counselor.pk).update(school=self.other_school)
        self.assertEqual(self.accept(token).status_code, 404)
        self.assertFalse(User.objects.filter(role=User.Role.ASSISTANT).exists())

    def test_weak_password_and_taken_username_are_refused(self):
        token = self.token_of(self.invite())
        self.assertEqual(self.accept(token, password='123').status_code, 400)
        self.assertEqual(self.accept(token, username='tom').status_code, 400)
        self.assertEqual(AssistantInvite.objects.get().status, 'active')


class AssistantStudentsTests(AssistantBase):
    def test_counselor_splits_their_students_and_can_replace_the_set(self):
        assistant = self.make_assistant()
        response = self.give(assistant, self.mine, self.also_mine)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(StudentProfile.objects.filter(assigned_assistant=assistant)), {self.mine, self.also_mine})
        self.give(assistant, self.also_mine)
        self.assertEqual(list(StudentProfile.objects.filter(assigned_assistant=assistant)), [self.also_mine])

        self.client.force_authenticate(self.counselor)
        listed = self.client.get('/api/assistants/').data['results']
        self.assertEqual([(row['id'], row['students_count']) for row in listed], [(assistant.pk, 1)])

    def test_assistants_are_paginated(self):
        for i in range(3):
            self.make_assistant(username=f'assistant{i}')
        self.client.force_authenticate(self.counselor)
        first = self.client.get('/api/assistants/?page_size=2').data
        second = self.client.get('/api/assistants/?page_size=2&page=2').data
        self.assertEqual(first['count'], 3)
        self.assertTrue(first['next'])
        self.assertEqual(len(first['results']), 2)
        self.assertEqual(len(second['results']), 1)

    def test_another_counselors_student_cannot_be_given(self):
        assistant = self.make_assistant()
        response = self.give(assistant, self.mine, self.colleagues)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentProfile.objects.filter(assigned_assistant=assistant).exists())

    def test_counselor_cannot_manage_another_counselors_assistant(self):
        assistant = self.make_assistant(self.colleague)
        self.assertEqual(self.give(assistant, self.mine).status_code, 404)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/assistants/{assistant.pk}/deactivate/').status_code, 404)
        self.assertEqual(self.client.get('/api/assistants/').data['results'], [])

    def test_student_profile_edit_cannot_set_the_assistant(self):
        assistant = self.make_assistant()
        self.client.force_authenticate(self.counselor)
        self.client.patch(f'/api/students/{self.mine.pk}/', {'assigned_assistant': assistant.pk}, format='json')
        self.mine.refresh_from_db()
        self.assertIsNone(self.mine.assigned_assistant)


class AssistantScopeTests(AssistantBase):
    def setUp(self):
        super().setUp()
        self.assistant = self.make_assistant()
        self.give(self.assistant, self.mine)
        self.client.force_authenticate(self.assistant)

    def test_assistant_lists_only_the_students_given_to_them(self):
        response = self.client.get('/api/students/')
        self.assertEqual([row['id'] for row in response.data['results']], [self.mine.pk])
        self.assertEqual(self.client.get(f'/api/students/{self.mine.pk}/').status_code, 200)
        for other in (self.also_mine, self.colleagues):
            with self.subTest(student=other.user.username):
                self.assertEqual(self.client.get(f'/api/students/{other.pk}/').status_code, 404)

    def test_assistant_reads_and_edits_counselor_notes_of_their_students(self):
        StudentProfile.objects.filter(pk=self.mine.pk).update(notes='Private counselor note')
        self.assertEqual(self.client.get(f'/api/students/{self.mine.pk}/').data['notes'], 'Private counselor note')
        response = self.client.patch(f'/api/students/{self.mine.pk}/', {'notes': 'Call parents'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.patch(f'/api/students/{self.also_mine.pk}/', {'notes': 'x'}, format='json').status_code, 404)

    def test_assistant_reads_shared_essays_letters_and_meetings_of_their_students_only(self):
        own = Essay.objects.create(student=self.mine, title='Why me', shared_with_counselor=True)
        Essay.objects.create(student=self.also_mine, title='Hidden', shared_with_counselor=True)
        Essay.objects.create(student=self.mine, title='Private draft')
        listed = self.client.get('/api/essays/').data
        self.assertEqual([row['id'] for row in listed.get('results', listed)], [own.pk])
        for path in ('/api/meetings/', '/api/recommendations/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_essay_lab_access_follows_the_assistants_students(self):
        from ..essay_lab.access import NONE, resolve_access

        own = Essay.objects.create(student=self.mine, title='Why me', shared_with_counselor=True)
        hidden = Essay.objects.create(student=self.also_mine, title='Hidden', shared_with_counselor=True)
        self.assertEqual(resolve_access(self.assistant, own), resolve_access(self.counselor, own))
        self.assertEqual(resolve_access(self.assistant, hidden), NONE)
        StudentProfile.objects.filter(pk=self.mine.pk).update(assigned_counselor=self.colleague)
        self.assertEqual(resolve_access(self.assistant, Essay.objects.get(pk=own.pk)), NONE)

    def test_assistant_assigns_and_approves_tasks_of_their_students_only(self):
        own = Task.objects.create(student=self.mine, assigned_by=self.counselor, title='Draft list', due_date=date(2027, 1, 1), status=Task.Status.SUBMITTED)
        other = Task.objects.create(student=self.also_mine, assigned_by=self.counselor, title='Hidden', due_date=date(2027, 1, 1), status=Task.Status.SUBMITTED)
        listed = self.client.get('/api/tasks/').data
        self.assertEqual([row['id'] for row in listed.get('results', listed)], [own.pk])
        self.assertEqual(self.client.get(f'/api/tasks/{other.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/tasks/{other.pk}/approve/', {}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'/api/tasks/{other.pk}/send-back/', {'note': 'Add dates.'}, format='json').status_code, 404)

        approved = self.client.post(f'/api/tasks/{own.pk}/approve/', {}, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        own.refresh_from_db()
        self.assertEqual(own.status, Task.Status.APPROVED)
        created = self.client.post('/api/tasks/', {'student': self.mine.pk, 'title': 'New', 'due_date': '2027-02-01'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        refused = self.client.post('/api/tasks/', {'student': self.also_mine.pk, 'title': 'New', 'due_date': '2027-02-01'}, format='json')
        self.assertIn(refused.status_code, {400, 403, 404})
        bulk = self.client.post('/api/tasks/bulk/', {'students': [self.mine.pk, self.also_mine.pk], 'title': 'All', 'due_date': '2027-02-01'}, format='json')
        self.assertEqual(bulk.status_code, 400)
        self.assertFalse(Task.objects.filter(student=self.also_mine, title__in=['New', 'All']).exists())

    def test_assistant_cannot_move_students_to_another_counselor_or_connect_them(self):
        moved = self.client.patch(f'/api/students/{self.mine.pk}/', {'assigned_counselor': self.colleague.pk}, format='json')
        self.assertEqual(moved.status_code, 400)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.assigned_counselor, self.counselor)
        self.assertEqual(self.client.post('/api/students/', {'school': self.school.pk}, format='json').status_code, 403)
        self.assertEqual(self.client.get('/api/students/assignment-candidates/').status_code, 403)
        self.assertEqual(self.client.post('/api/students/assign-counselor/', {'students': [self.colleagues.pk]}, format='json').status_code, 403)

    def test_assistant_adds_a_student_for_their_counselor_and_themselves(self):
        quick = {'name': 'New Student', 'email': 'new@example.com', 'phone': '+998901234567'}
        elsewhere = self.client.post('/api/students/quick-create/', {**quick, 'school': self.other_school.pk}, format='json')
        self.assertEqual(elsewhere.status_code, 400)
        response = self.client.post('/api/students/quick-create/', quick, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['temporary_password'])
        added = StudentProfile.objects.get(pk=response.data['id'])
        self.assertEqual((added.school, added.assigned_counselor, added.assigned_assistant), (self.school, self.counselor, self.assistant))
        self.assertEqual(self.client.get(f'/api/students/{added.pk}/').status_code, 200)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'/api/students/{added.pk}/').status_code, 200)

    def test_assistant_without_a_counselor_cannot_add_students(self):
        User.objects.filter(pk=self.assistant.pk).update(supervising_counselor=None)
        self.assistant.refresh_from_db()
        self.client.force_authenticate(self.assistant)
        quick = {'name': 'New Student', 'email': 'new@example.com', 'phone': '+998901234567'}
        self.assertEqual(self.client.post('/api/students/quick-create/', quick, format='json').status_code, 400)
        self.assertFalse(User.objects.filter(email='new@example.com').exists())

    def test_a_student_moved_to_another_counselor_drops_out(self):
        StudentProfile.objects.filter(pk=self.mine.pk).update(assigned_counselor=self.colleague)
        self.assertEqual(self.client.get(f'/api/students/{self.mine.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/api/students/').data['results'], [])

    def test_assistant_messages_their_students_and_school_staff_only(self):
        other_school_student = self.make_student('zafar', None, self.other_school)
        ids = {row['id'] for row in self.client.get('/api/message-channels/contacts/').data}
        self.assertIn(self.mine.user_id, ids)
        self.assertIn(self.counselor.pk, ids)
        self.assertIn(self.teacher.pk, ids)
        self.assertNotIn(self.also_mine.user_id, ids)
        self.assertNotIn(other_school_student.user_id, ids)

    def test_unassigned_students_cannot_start_a_chat_with_the_assistant(self):
        self.client.force_authenticate(self.also_mine.user)
        contacts = self.client.get('/api/message-channels/contacts/').data
        self.assertNotIn(self.assistant.pk, {row['id'] for row in contacts})
        response = self.client.post('/api/message-channels/direct/', {'user': self.assistant.pk}, format='json')
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.mine.user)
        contacts = self.client.get('/api/message-channels/contacts/').data
        self.assertIn(self.assistant.pk, {row['id'] for row in contacts})

    def test_another_schools_students_and_records_stay_out_of_reach(self):
        south_counselor = User.objects.create_user('sam', 'sam@example.com', PASSWORD, role=User.Role.COUNSELOR, school=self.other_school)
        south = self.make_student('sardor', south_counselor, self.other_school)
        south_task = Task.objects.create(student=south, assigned_by=south_counselor, title='South task', due_date=date(2027, 1, 1))
        # Even a stale assistant pointer on a foreign student does not pull it in.
        StudentProfile.objects.filter(pk=south.pk).update(assigned_assistant=self.assistant)
        self.assertEqual(self.client.get(f'/api/students/{south.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/tasks/{south_task.pk}/').status_code, 404)
        self.assertEqual([row['id'] for row in self.client.get('/api/students/').data['results']], [self.mine.pk])
        # A given student who moves to another school drops out too.
        StudentProfile.objects.filter(pk=self.mine.pk).update(school=self.other_school)
        self.assertEqual(self.client.get('/api/students/').data['results'], [])
        # The other school's counselor cannot reach this assistant.
        self.assertEqual(self.give(self.assistant, south, counselor=south_counselor).status_code, 404)

    def test_an_inactive_or_transferred_supervisor_removes_student_access(self):
        for changes in ({'is_active': False}, {'school': self.other_school}, {'role': User.Role.TEACHER}):
            with self.subTest(changes=changes):
                User.objects.filter(pk=self.counselor.pk).update(**changes)
                self.assertEqual(self.client.get('/api/students/').data['results'], [])
                User.objects.filter(pk=self.counselor.pk).update(
                    is_active=True, school=self.school, role=User.Role.COUNSELOR,
                )

    def test_assistant_approves_roadmap_missions_of_their_students_only(self):
        own = RoadmapMission.objects.create(
            student=self.mine, assigned_by=self.counselor, title='Shortlist',
            status=RoadmapMission.Status.SUBMITTED, reflection='My shortlist',
        )
        other = RoadmapMission.objects.create(
            student=self.also_mine, assigned_by=self.counselor, title='Hidden',
            status=RoadmapMission.Status.SUBMITTED, reflection='Hidden',
        )
        self.assertEqual(self.client.post(f'/api/roadmap-missions/{other.pk}/approve/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/roadmap-missions/{own.pk}/approve/').status_code, 200)
        own.refresh_from_db()
        self.assertEqual(own.status, RoadmapMission.Status.COMPLETED)

    def test_assistant_dashboard_has_the_counselor_numbers_over_their_students(self):
        Essay.objects.create(student=self.mine, title='Why me', shared_with_counselor=True, status=Essay.Status.NEEDS_REVISION)
        Essay.objects.create(student=self.also_mine, title='Hidden', shared_with_counselor=True, status=Essay.Status.NEEDS_REVISION)
        response = self.client.get('/api/dashboard/stats/', {'include': 'home'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['students_total'], 1)
        self.assertEqual(response.data['essays_need_revision'], 1)
        self.assertIn('home', response.data)
        self.assertEqual(self.client.get('/api/dashboard/stats/', {'snapshot': self.also_mine.pk}).status_code, 404)

    def test_assistant_books_meetings_with_their_students_only(self):
        start = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
        booking = {'topic': 'Shortlist', 'starts_at': start.isoformat(), 'duration_minutes': 30}
        own = self.client.post('/api/bookings/', {**booking, 'student': self.mine.pk}, format='json')
        self.assertEqual(own.status_code, 201, own.data)
        self.assertEqual(own.data['participant'], self.assistant.pk)
        later = (start + timedelta(hours=2)).isoformat()
        other = self.client.post('/api/bookings/', {**booking, 'starts_at': later, 'student': self.also_mine.pk}, format='json')
        self.assertEqual(other.status_code, 400)
        listed = self.client.get('/api/bookings/').data
        self.assertEqual([row['id'] for row in listed.get('results', listed)], [own.data['id']])

    def test_assistant_without_a_counselor_sees_nobody(self):
        User.objects.filter(pk=self.assistant.pk).update(supervising_counselor=None)
        self.assistant.refresh_from_db()
        self.client.force_authenticate(self.assistant)
        self.assertEqual(self.client.get('/api/students/').data['results'], [])

    def test_deactivated_assistant_loses_students_and_sign_in(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/assistants/{self.assistant.pk}/deactivate/')
        self.assertEqual(response.data, {'id': self.assistant.pk, 'is_active': False})
        self.assertFalse(StudentProfile.objects.filter(assigned_assistant=self.assistant).exists())
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/token/', {'username': 'aziza', 'password': PASSWORD}, format='json')
        self.assertNotEqual(login.status_code, 200)

    def test_assistant_cannot_manage_assistants(self):
        self.assertEqual(self.client.get('/api/assistants/').status_code, 403)
        self.assertEqual(self.client.get('/api/assistant-invites/').status_code, 403)
