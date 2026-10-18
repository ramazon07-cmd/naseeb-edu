"""Parent portal payload, visibility and write rules (Trello parent cards)."""
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import Booking, ParentStudentLink, ScreenTimeDaily, StudentProfile, Task
from .base import RoleIsolationBase

PORTAL = '/api/parent-portal/'


class ParentPortalTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.parent = User.objects.create_user(
            username='portal-parent', email='portal-parent@example.com',
            password='StrongParent123!', role=User.Role.PARENT,
        )
        self.link = ParentStudentLink.objects.create(
            parent=self.parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        self.client.force_authenticate(self.parent)

    def portal(self):
        response = self.client.get(PORTAL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def child(self, student=None):
        student = student or self.student_a
        return next((item for item in self.portal()['children'] if item['profile']['id'] == student.id), None)

    def test_pending_level_up_is_reported_instead_of_xp_over_the_threshold(self):
        StudentProfile.objects.filter(pk=self.student_a.pk).update(level=1, xp_total=350)
        profile = self.child()['profile']
        self.assertTrue(profile['level_up_pending'])
        self.assertEqual(profile['eligible_level'], 3)
        StudentProfile.objects.filter(pk=self.student_a.pk).update(level=2, xp_total=150)
        profile = self.child()['profile']
        self.assertFalse(profile['level_up_pending'])
        self.assertEqual(profile['next_level_xp'], 300)
        self.assertEqual(profile['xp_progress_percent'], 25)

    def test_meetings_say_whether_an_unconfirmed_request_expired(self):
        expired = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Missed request',
            starts_at=timezone.now() - timedelta(hours=2),
        )
        upcoming = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Next check-in',
            starts_at=timezone.now() + timedelta(days=2),
        )
        meetings = {item['id']: item for item in self.child()['meetings']}
        self.assertTrue(meetings[expired.id]['is_expired'])
        self.assertFalse(meetings[upcoming.id]['is_expired'])

    def test_deactivated_child_or_school_is_hidden_until_reactivated(self):
        self.student_a_user.is_active = False
        self.student_a_user.save(update_fields=['is_active'])
        self.assertIsNone(self.child())
        self.student_a_user.is_active = True
        self.student_a_user.save(update_fields=['is_active'])
        StudentProfile.objects.filter(pk=self.student_a.pk).update(deactivated_at=timezone.now())
        self.assertIsNone(self.child())
        StudentProfile.objects.filter(pk=self.student_a.pk).update(deactivated_at=None)
        self.school_a.is_active = False
        self.school_a.save(update_fields=['is_active'])
        self.assertIsNone(self.child())
        contacts = self.client.get('/api/message-channels/contacts/')
        self.assertNotIn(self.counselor.id, {item['id'] for item in contacts.data})
        self.school_a.is_active = True
        self.school_a.save(update_fields=['is_active'])
        self.assertIsNotNone(self.child())

    def test_invitation_for_a_deactivated_student_cannot_be_accepted(self):
        self.link.status = ParentStudentLink.Status.PENDING
        self.link.save(update_fields=['status'])
        StudentProfile.objects.filter(pk=self.student_a.pk).update(deactivated_at=timezone.now())
        response = self.client.post(f'/api/parent-links/{self.link.id}/accept/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, ParentStudentLink.Status.PENDING)

    def test_parents_have_no_screen_time(self):
        track = self.client.post('/api/screen-time/track/', {'entries': [{'page': 'dashboard', 'seconds': 30}]}, format='json')
        self.assertEqual(track.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/screen-time/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/screen-time/summary/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ScreenTimeDaily.objects.filter(user=self.parent).exists())

    def test_cleanup_migration_deletes_only_parent_rows(self):
        from importlib import import_module
        from django.apps import apps as django_apps
        from django.db import connection
        from types import SimpleNamespace
        today = timezone.localdate()
        ScreenTimeDaily.objects.create(user=self.parent, date=today, page='dashboard', active_seconds=120)
        ScreenTimeDaily.objects.create(user=self.student_a_user, date=today, page='dashboard', active_seconds=60)
        migration = import_module('apps.admissions.migrations.0079_delete_parent_screen_time')
        self.assertEqual(migration.Migration.dependencies, [('admissions', '0078_student_invites')])
        migration.delete_parent_rows(django_apps, SimpleNamespace(connection=connection))
        self.assertEqual(list(ScreenTimeDaily.objects.values_list('user_id', flat=True)), [self.student_a_user.id])

    def test_parent_cannot_write_through_any_router_endpoint(self):
        from apps.admissions.urls import router
        # Parent writes are an allow-list: direct chats, their own links, their own alerts.
        allowed = {'message-channels', 'channel-messages', 'parent-links', 'notifications'}
        leaks = []
        for prefix, _viewset, _basename in router.registry:
            if prefix in allowed:
                continue
            response = self.client.post(f'/api/{prefix}/', {'student': self.student_a.id}, format='json')
            if response.status_code not in {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED}:
                leaks.append(f'POST /api/{prefix}/ -> {response.status_code}')
        for path in (f'/api/students/{self.student_a.id}/', '/api/students/onboarding/'):
            response = self.client.patch(path, {'notes': 'parent edit'}, format='json')
            if response.status_code != status.HTTP_403_FORBIDDEN:
                leaks.append(f'PATCH {path} -> {response.status_code}')
        self.assertEqual(leaks, [])

    def add_child(self, username):
        user = User.objects.create_user(
            username=username, email=f'{username}@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_a,
        )
        profile = StudentProfile.objects.create(
            user=user, school=self.school_a, school_name=self.school_a.name, assigned_counselor=self.counselor,
        )
        ParentStudentLink.objects.create(
            parent=self.parent, student=profile, status=ParentStudentLink.Status.ACTIVE, consented_at=timezone.now(),
        )
        Task.objects.create(student=profile, assigned_by=self.counselor, title='Open work', due_date=timezone.localdate())
        Booking.objects.create(
            student=profile, participant=self.counselor, topic='Check-in', starts_at=timezone.now() + timedelta(days=1),
        )
        return profile

    def test_query_count_does_not_grow_with_children(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as one_child:
            self.portal()
        self.add_child('second-child')
        self.add_child('third-child')
        with CaptureQueriesContext(connection) as three_children:
            self.assertEqual(len(self.portal()['children']), 3)
        self.assertEqual(len(three_children), len(one_child))

    def test_closed_tasks_are_capped_but_open_tasks_are_all_returned(self):
        from ..views.parents import ParentPortalView
        limit = ParentPortalView.CLOSED_TASKS
        Task.objects.bulk_create([
            Task(student=self.student_a, assigned_by=self.counselor, title=f'Done {index}', status=Task.Status.APPROVED, due_date=timezone.localdate())
            for index in range(limit + 5)
        ] + [Task(student=self.student_a, assigned_by=self.counselor, title=f'Open {index}', due_date=timezone.localdate()) for index in range(3)])
        statuses = [task['status'] for task in self.child()['tasks']]
        self.assertEqual(statuses.count(Task.Status.APPROVED), limit)
        self.assertEqual(statuses.count(Task.Status.TODO), 3)

    def test_parent_edits_own_name_phone_and_password_only(self):
        own = self.client.patch(f'/api/users/accounts/{self.parent.id}/', {'first_name': 'Dilnoza', 'phone': '+998901234567'}, format='json')
        self.assertEqual(own.status_code, status.HTTP_200_OK, own.data)
        other = self.client.patch(f'/api/users/accounts/{self.counselor.id}/', {'first_name': 'Changed'}, format='json')
        self.assertIn(other.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
        wrong = self.client.post('/api/users/accounts/me/password/', {
            'current_password': 'not-my-password', 'new_password': 'NewParentPass456!', 'confirm_password': 'NewParentPass456!',
        }, format='json')
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        changed = self.client.post('/api/users/accounts/me/password/', {
            'current_password': 'StrongParent123!', 'new_password': 'NewParentPass456!', 'confirm_password': 'NewParentPass456!',
        }, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK, changed.data)
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.check_password('NewParentPass456!'))

    def test_headline_counts_follow_metrics_and_hide_unshared_sections(self):
        from ..models import Application, University
        university = University.objects.create(name='Portal University', country='USA')
        for state in ('submitted', 'waitlisted', 'accepted', 'rejected'):
            Application.objects.create(student=self.student_a, university=university, program=state, status=state)
        Task.objects.create(student=self.student_a, assigned_by=self.counselor, title='Late', due_date=timezone.localdate() - timedelta(days=1))
        Task.objects.create(student=self.student_a, assigned_by=self.counselor, title='Done', status=Task.Status.APPROVED, due_date=timezone.localdate())
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Asked', starts_at=timezone.now() + timedelta(days=1))
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Off', starts_at=timezone.now() + timedelta(days=1), status=Booking.Status.CANCELLED)
        profile = self.child()['profile']
        self.assertEqual((profile['open_tasks_total'], profile['overdue_tasks_total']), (1, 1))
        self.assertEqual(profile['active_applications_total'], 2)
        self.assertEqual(profile['upcoming_meetings_total'], 1)
        self.link.can_view_applications = False
        self.link.can_view_meetings = False
        self.link.save(update_fields=['can_view_applications', 'can_view_meetings'])
        profile = self.child()['profile']
        self.assertIsNone(profile['active_applications_total'])
        self.assertIsNone(profile['upcoming_meetings_total'])

    def use_plan(self, school, parent_portal):
        from apps.users.models import PLAN_FEATURES, Plan, WorkspaceSubscription
        features = {key: True for key in PLAN_FEATURES}
        features['parent_portal'] = parent_portal
        plan, _ = Plan.objects.update_or_create(code=f'parents-{parent_portal}', defaults={'name': 'Parents', 'features': features})
        WorkspaceSubscription.objects.filter(school=school).update(plan=plan)

    def test_invite_is_refused_when_the_school_plan_has_no_parent_portal(self):
        self.use_plan(self.school_a, parent_portal=False)
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/parent-links/invite/', {
            'student': self.student_a.id, 'email': 'blocked-parent@example.com', 'first_name': 'Blocked',
            'password': 'StrongParent123!', 'relationship': ParentStudentLink.Relationship.MOTHER,
            'can_view_applications': True, 'can_view_documents': True, 'can_view_meetings': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'feature_not_in_plan')
        self.assertFalse(User.objects.filter(email='blocked-parent@example.com').exists())

    def test_each_child_counts_on_its_own_school_plan(self):
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student_b, status=ParentStudentLink.Status.ACTIVE, consented_at=timezone.now(),
        )
        self.use_plan(self.school_a, parent_portal=True)
        self.use_plan(self.school_b, parent_portal=False)
        portal = self.portal()
        self.assertEqual([child['profile']['id'] for child in portal['children']], [self.student_a.id])
        self.assertEqual(portal['plan_locked_children'], 1)
        self.use_plan(self.school_a, parent_portal=False)
        portal = self.portal()
        self.assertEqual((portal['children'], portal['plan_locked_children']), ([], 2))

    def test_a_school_without_a_subscription_keeps_the_parent_portal(self):
        from apps.users.models import WorkspaceSubscription
        WorkspaceSubscription.objects.filter(school=self.school_a).delete()
        self.assertIsNotNone(self.child())

    def test_counselor_changes_shared_sections_on_an_active_link(self):
        from apps.users.models import ProductAuditEvent
        url = f'/api/parent-links/{self.link.id}/sections/'
        self.assertEqual(self.client.post(url, {'can_view_documents': False}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.counselor_b)
        self.assertIn(self.client.post(url, {'can_view_documents': False}, format='json').status_code, {403, 404})
        self.client.force_authenticate(self.counselor)
        listed = self.results(self.client.get(f'/api/parent-links/?student={self.student_a.id}'))
        self.assertEqual([item['id'] for item in listed], [self.link.id])
        changed = self.client.post(url, {'can_view_documents': False, 'status': 'revoked'}, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK, changed.data)
        self.link.refresh_from_db()
        self.assertEqual((self.link.can_view_documents, self.link.status), (False, ParentStudentLink.Status.ACTIVE))
        self.assertEqual(ProductAuditEvent.objects.filter(action='parent.permissions_changed').count(), 1)
        self.client.force_authenticate(self.parent)
        child = self.child()
        self.assertEqual((child['permissions']['documents'], child['documents']), (False, []))

    def test_parent_opens_a_direct_chat_with_the_childs_counselor_only(self):
        opened = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json')
        self.assertIn(opened.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED}, opened.data)
        self.assertNotIn(
            self.client.post('/api/message-channels/direct/', {'user': self.counselor_b.id}, format='json').status_code,
            {status.HTTP_200_OK, status.HTTP_201_CREATED},
        )
        self.assertNotIn(
            self.client.post('/api/message-channels/', {'kind': 'group', 'name': 'Parents'}, format='json').status_code,
            {status.HTTP_200_OK, status.HTTP_201_CREATED},
        )
