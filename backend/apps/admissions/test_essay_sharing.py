"""Essays are private to their student until shared with the counselor."""
import json

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import ProductAuditEvent, User
from .assistant import build_role_context
from .models import ActivityLog, Essay, EssayRevision, Notification, ParentStudentLink, StudentProfile
from .test_audit_base import AuditBaseMixin

LAB = '/api/essay-lab/essays'
SECRET = 'Grandmother bread secret'


class EssaySharingTestCase(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        self.essay = Essay.objects.create(
            student=self.student, title=SECRET, prompt='Why us?', content='Draft text.',
            status=Essay.Status.NEEDS_REVISION,
        )

    def as_student(self):
        self.client.force_authenticate(self.student_user)

    def share(self, essay=None, action='share'):
        self.as_student()
        return self.client.post(f'{LAB}/{(essay or self.essay).pk}/{action}/')

    def unshare(self, essay=None):
        return self.share(essay, 'unshare')

    def seen_by(self, user):
        """Every way ``user`` could come across the essay, as {path: bool}."""
        self.client.force_authenticate(user)
        listing = self.client.get('/api/essays/')
        rows = self.results(listing) if listing.status_code == 200 else []
        detail = self.client.get(f'/api/essays/{self.essay.pk}/')
        search = self.client.get('/api/search/', {'q': 'Grandmother'})
        found = search.data.get('results', {}).get('essays', []) if search.status_code == 200 else []
        seen = {
            'list': any(row['id'] == self.essay.pk for row in rows),
            'detail': detail.status_code == status.HTTP_200_OK,
            'search': bool(found),
        }
        stats = self.client.get('/api/dashboard/stats/')
        if stats.status_code == 200 and 'essays_need_revision' in stats.data:
            seen['count'] = stats.data['essays_need_revision'] > 0
        if user.is_product_admin or user.is_organization:
            visibility = self.client.get(f'/api/students/{self.student.pk}/data-visibility/')
            seen['visibility'] = bool(visibility.data['essays'])
        if user.role == User.Role.PARENT:
            portal = self.client.get('/api/parent-portal/')
            seen['parent_portal'] = SECRET in json.dumps(portal.data, default=str)
        return seen


class EssayVisibilityTests(EssaySharingTestCase):
    def assert_seen(self, user, expected):
        seen = self.seen_by(user)
        self.assertTrue(seen, user.username)
        for path, value in seen.items():
            with self.subTest(user=user.username, path=path):
                self.assertEqual(value, expected)

    def test_only_shared_essays_reach_staff_and_admins(self):
        for user in (self.counselor, self.organization, self.admin):
            self.assert_seen(user, False)
        self.assertEqual(self.share().status_code, status.HTTP_200_OK)
        for user in (self.counselor, self.organization, self.admin):
            self.assert_seen(user, True)
        self.assertEqual(self.unshare().status_code, status.HTTP_200_OK)
        for user in (self.counselor, self.organization, self.admin):
            self.assert_seen(user, False)

    def test_sharing_never_widens_the_normal_scope(self):
        self.share()
        for user in (self.counselor_peer, self.counselor_b, self.parent, self.teacher):
            self.assert_seen(user, False)

    def test_owner_always_sees_every_own_essay(self):
        self.as_student()
        self.assertEqual(self.client.get(f'/api/essays/{self.essay.pk}/').status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in self.client.get(f'{LAB}/').data], [self.essay.pk])
        self.assertEqual(self.client.get('/api/dashboard/stats/').data['essays_need_revision'], 1)

    def test_counselor_feedback_survives_unshare_but_is_hidden_until_reshared(self):
        self.share()
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(
            f'/api/essays/{self.essay.pk}/', {'counselor_comment': 'Tighten the ending.'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.unshare()
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'/api/essays/{self.essay.pk}/').status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.patch(f'/api/essays/{self.essay.pk}/', {'counselor_comment': 'x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.essay.refresh_from_db()
        self.assertEqual(self.essay.counselor_comment, 'Tighten the ending.')
        self.share()
        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/essays/{self.essay.pk}/')
        self.assertEqual(detail.data['counselor_comment'], 'Tighten the ending.')
        self.assertEqual([revision['version'] for revision in detail.data['revisions']], [2])

    def test_assistant_context_never_carries_a_private_essay(self):
        for user in (self.counselor, self.student_user):
            self.assertNotIn(SECRET, json.dumps(build_role_context(user), default=str))

    def test_private_essays_raise_no_notifications(self):
        call_command('generate_notifications', verbosity=0)
        self.assertFalse(Notification.objects.filter(message__contains=SECRET).exists())
        self.assertFalse(Notification.objects.filter(title__icontains='essay').exists())

    def test_staff_created_essay_starts_shared(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/essays/', {
            'student': self.student.pk, 'title': 'Assigned essay', 'prompt': 'Describe a challenge.',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['shared_with_counselor'])
        self.assertEqual(self.client.get(f"/api/essays/{response.data['id']}/").status_code, status.HTTP_200_OK)

    def test_student_created_essay_starts_private(self):
        self.as_student()
        legacy = self.client.post('/api/essays/', {'student': self.student.pk, 'title': 'Mine', 'prompt': 'P'},
                                  format='json')
        lab = self.client.post(f'{LAB}/', {'title': 'Lab essay'}, format='json')
        self.assertFalse(legacy.data['shared_with_counselor'])
        self.assertFalse(lab.data['shared_with_counselor'])
        self.assertFalse(Essay.objects.filter(pk__in=[legacy.data['id'], lab.data['id']], shared_with_counselor=True))

    def test_every_tab_of_a_shared_document_reaches_the_counselor(self):
        self.as_student()
        essay = self.client.post(f'{LAB}/', {'title': 'Tabbed'}, format='json').data
        tab = self.client.post(f"{LAB}/{essay['id']}/tabs/", {'title': 'Draft two'}, format='json').data['tab']
        saved = self.client.put(f"{LAB}/{essay['id']}/autosave/", {
            'doc': {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Tab two.'}]}]},
            'base_seq': 0, 'client_save_id': 'two', 'tab': tab['id'],
        }, format='json')
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f"/api/essays/{essay['id']}/").status_code, status.HTTP_404_NOT_FOUND)
        self.share(Essay.objects.get(pk=essay['id']))
        self.client.force_authenticate(self.counselor)
        self.assertIn('Tab two.', self.client.get(f"/api/essays/{essay['id']}/").data['content'])
        # Counselors never reach the student's editor API.
        self.assertEqual(self.client.get(f"{LAB}/{essay['id']}/").status_code, status.HTTP_403_FORBIDDEN)


class ShareActionTests(EssaySharingTestCase):
    def test_share_records_once_and_notifies_the_counselor(self):
        before = Essay.objects.values_list('updated_at', flat=True).get(pk=self.essay.pk)
        first = self.share()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['shared_with_counselor'])
        self.assertIsNotNone(first.data['shared_at'])
        again = self.share()
        self.assertEqual(again.data['shared_at'], first.data['shared_at'])
        self.essay.refresh_from_db()
        self.assertTrue(self.essay.shared_with_counselor)
        self.assertEqual(self.essay.updated_at, before)
        log = ActivityLog.objects.get(student=self.student, metadata__event='essay.shared')
        self.assertEqual(log.metadata['essay'], self.essay.pk)
        audit = ProductAuditEvent.objects.get(action='essay.shared')
        self.assertEqual((audit.target_id, audit.metadata['essay']), (str(self.student.pk), self.essay.pk))
        notification = Notification.objects.get(student=self.student)
        self.assertEqual(notification.title, 'Essay shared with counselor')
        self.assertEqual((notification.kind, notification.target_id), (Notification.Kind.ESSAY, self.essay.pk))
        # Nothing written names the essay, so an unshare leaves no trace of it for staff.
        self.assertNotIn(SECRET, f'{notification.title} {notification.message} {log.action} {audit.target_label}')
        # The assigned counselor sees it through the usual notifications list.
        self.client.force_authenticate(self.counselor)
        self.assertEqual([row['id'] for row in self.results(self.client.get('/api/notifications/'))], [notification.pk])

    def test_unshare_is_idempotent_and_does_not_notify(self):
        self.share()
        Notification.objects.all().delete()
        for _ in range(2):
            response = self.unshare()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertFalse(response.data['shared_with_counselor'])
            self.assertIsNone(response.data['shared_at'])
        self.assertEqual(ProductAuditEvent.objects.filter(action='essay.unshared').count(), 1)
        self.assertEqual(ActivityLog.objects.filter(metadata__event='essay.unshared').count(), 1)
        self.assertFalse(Notification.objects.exists())

    def test_share_without_a_counselor_writes_no_notification(self):
        StudentProfile.objects.filter(pk=self.student.pk).update(assigned_counselor=None)
        self.assertEqual(self.share().status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.exists())

    def test_another_students_essay_looks_missing(self):
        foreign = Essay.objects.create(student=self.student_b, title='Not yours')
        for action in ('share', 'unshare'):
            self.assertEqual(self.share(foreign, action).status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertFalse(foreign.shared_with_counselor)

    def test_staff_cannot_toggle_sharing(self):
        self.share()
        for user in (self.counselor, self.organization, self.admin, self.teacher, self.parent):
            self.client.force_authenticate(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.post(f'{LAB}/{self.essay.pk}/unshare/').status_code,
                                 status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.counselor)
        self.client.patch(f'/api/essays/{self.essay.pk}/', {'shared_with_counselor': False, 'shared_at': None},
                          format='json')
        self.essay.refresh_from_db()
        self.assertTrue(self.essay.shared_with_counselor)
        self.assertIsNotNone(self.essay.shared_at)
        # A student can't flip it through the legacy API either.
        self.as_student()
        self.client.patch(f'/api/essays/{self.essay.pk}/', {'shared_with_counselor': False}, format='json')
        self.essay.refresh_from_db()
        self.assertTrue(self.essay.shared_with_counselor)

    def test_share_query_count_is_bounded(self):
        self.as_student()
        with CaptureQueriesContext(connection) as context:
            response = self.client.post(f'{LAB}/{self.essay.pk}/share/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Lock+read, update, activity log, audit event, notification (plus savepoints).
        writes = [q['sql'] for q in context.captured_queries if not q['sql'].startswith(('SAVEPOINT', 'RELEASE'))]
        self.assertLessEqual(len(writes), 6, writes)


class SharedEssayListQueryCountTests(EssaySharingTestCase):
    def add(self, count):
        for index in range(count):
            for shared in (True, False):
                essay = Essay.objects.create(
                    student=self.student, title=f'Essay {index} {shared}', shared_with_counselor=shared,
                    status=Essay.Status.NEEDS_REVISION,
                )
                EssayRevision.objects.create(
                    essay=essay, version=1, prompt='', status='draft', created_by=self.counselor,
                )

    def test_staff_lists_are_filtered_in_constant_queries(self):
        for url, bound in (('/api/essays/', 6), ('/api/dashboard/stats/', 13)):
            for user in (self.counselor, self.admin):
                self.client.force_authenticate(user)
                with self.subTest(url=url, user=user.username):
                    Essay.objects.exclude(pk=self.essay.pk).delete()
                    self.add(2)
                    few, _ = self.get_counted(url)
                    self.add(6)
                    self.client.force_authenticate(user)
                    many, response = self.get_counted(url)
                    self.assertEqual(few, many)
                    self.assertLessEqual(many, bound)
                    if url == '/api/essays/':
                        self.assertEqual(response.data['count'], 8)
                        self.assertTrue(all(row['shared_with_counselor'] for row in self.results(response)))
                    elif 'essays_need_revision' in response.data:
                        self.assertEqual(response.data['essays_need_revision'], 8)

    def get_counted(self, url, expected_status=200):
        from django.core.cache import cache

        cache.clear()
        return super().get_counted(url, expected_status)


class ShareEngagedEssaysMigrationTests(TransactionTestCase):
    migrate_from = [('admissions', '0053_tabs_essay_tabs_required')]
    migrate_to = [('admissions', '0054_share_essay_sharing')]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_only_essays_a_counselor_engaged_with_become_shared(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldSchool = old_apps.get_model('admissions', 'School')
        OldUser = old_apps.get_model('users', 'User')
        OldProfile = old_apps.get_model('admissions', 'StudentProfile')
        OldEssay = old_apps.get_model('admissions', 'Essay')
        OldRevision = old_apps.get_model('admissions', 'EssayRevision')
        school = OldSchool.objects.create(name='Sharing school', code='sharing-school')
        counselor = OldUser.objects.create(username='share-c', email='share-c@example.com', role='counselor', school=school)
        student_user = OldUser.objects.create(username='share-s', email='share-s@example.com', role='student', school=school)
        profile = OldProfile.objects.create(user=student_user, school=school, assigned_counselor=counselor)

        def essay(title, **values):
            return OldEssay.objects.create(student=profile, title=title, **values)

        private = essay('Private draft')
        OldRevision.objects.create(essay=private, version=1, prompt='', status='draft', created_by=student_user)
        orphan = essay('Author deleted')
        OldRevision.objects.create(essay=orphan, version=1, prompt='', status='draft', created_by=None)
        reviewed = essay('Reviewed', status='reviewing')
        commented = essay('Commented', counselor_comment='Good start.')
        revised = essay('Counselor revision')
        OldRevision.objects.create(essay=revised, version=1, prompt='', status='draft', created_by=student_user)
        OldRevision.objects.create(essay=revised, version=2, prompt='', status='draft', created_by=counselor)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        rows = {
            row.title: row for row in new_apps.get_model('admissions', 'Essay').objects.all()
        }
        self.assertEqual(
            {title for title, row in rows.items() if row.shared_with_counselor},
            {'Reviewed', 'Commented', 'Counselor revision'},
        )
        for row in rows.values():
            self.assertEqual(row.shared_at, row.updated_at if row.shared_with_counselor else None)
