"""Cross-tenant probe: every actor, every read path, before and after moves.

Two organization schools and one individual counselor workspace. After each
step (student move, counselor transfer, parent link changes) every non-admin
actor is probed through the API, and nothing they can see may belong to a
tenant other than their own.

The endpoint sweep then gives every student one record of every kind and
checks, for every role, every list, detail, file and write path: another
tenant's rows never show up, another tenant's ids behave exactly like ids
that do not exist, and no id in a request body can attach another tenant's
student, record, staff member or channel.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User

from .assistant import build_role_context
from .models import (
    Achievement,
    Activity,
    ActivityLog,
    Application,
    Booking,
    ChallengeAttempt,
    ChannelMembership,
    ChannelMessage,
    Document,
    Essay,
    EssayFolder,
    Honor,
    Internship,
    MeetingNote,
    MessageChannel,
    Notification,
    ParentStudentLink,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    RoadmapMission,
    School,
    StudentMessage,
    StudentProfile,
    Task,
    University,
)
from .scoping import tenant_school_id

PASSWORD = 'StrongPass123!'


class CrossTenantFixture:
    """Two organization schools and one individual workspace, one student each."""

    def setUp(self):
        self.school_a = School.objects.create(name='Probe A', code='probe-a')
        self.school_b = School.objects.create(name='Probe B', code='probe-b')
        self.admin = self.user('probe-admin', User.Role.ADMIN, None)
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/users/accounts/create-individual-counselor/', {
            'username': 'probe-solo', 'email': 'probe-solo@example.com', 'password': PASSWORD, 'first_name': 'Solo',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.solo = User.objects.get(username='probe-solo')
        self.workspace = self.solo.school

        self.counselor_a = self.user('probe-counselor-a', User.Role.COUNSELOR, self.school_a)
        self.org_a = self.user('probe-org-a', User.Role.ORGANIZATION, self.school_a)
        self.teacher_a = self.user('probe-teacher-a', User.Role.TEACHER, self.school_a)
        self.counselor_b = self.user('probe-counselor-b', User.Role.COUNSELOR, self.school_b)
        self.org_b = self.user('probe-org-b', User.Role.ORGANIZATION, self.school_b)
        self.student_a = self.student('probe-student-a', self.school_a, self.counselor_a)
        self.student_b = self.student('probe-student-b', self.school_b, self.counselor_b)
        self.student_w = self.student('probe-student-w', self.workspace, self.solo)

        self.parent = self.user('probe-parent', User.Role.PARENT, None)
        self.pending_parent = self.user('probe-pending-parent', User.Role.PARENT, None)
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        ParentStudentLink.objects.create(parent=self.pending_parent, student=self.student_b)

        for school, owner in ((self.school_a, self.teacher_a), (self.school_b, self.org_b)):
            community = MessageChannel.objects.create(
                kind=MessageChannel.Kind.COMMUNITY, name=f'{school.code} community', school=school, is_public=True,
            )
            ChannelMembership.objects.create(channel=community, user=owner, role=ChannelMembership.Role.OWNER)
        self.global_room = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Everyone', is_public=True, is_global=True, created_by=self.admin,
        )
        for profile in (self.student_a, self.student_b, self.student_w):
            counselor = profile.assigned_counselor
            Booking.objects.create(
                student=profile, participant=counselor, topic='Probe meeting',
                starts_at=timezone.now() + timedelta(days=3),
            )
            StudentMessage.objects.create(student=profile, sender=counselor, recipient=profile.user, body='Probe')
        # Staff and students join their school's channels; the student-A group
        # and the parent chat are the ties a move must cut.
        self.group_a = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='A group', school=self.school_a)
        for member in (self.teacher_a, self.student_a.user, self.counselor_a):
            ChannelMembership.objects.create(channel=self.group_a, user=member)
        self.client.force_authenticate(self.parent)
        self.parent_chat = self.client.post(
            '/api/message-channels/direct/', {'user': self.counselor_a.id}, format='json',
        ).data['id']

    # -- fixtures ---------------------------------------------------------

    def user(self, username, role, school):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password=PASSWORD, role=role, school=school,
        )

    def student(self, username, school, counselor):
        account = self.user(username, User.Role.STUDENT, school)
        return StudentProfile.objects.create(
            user=account, school=school, school_name=school.name, assigned_counselor=counselor,
        )

    def fresh(self, account):
        return User.objects.select_related('school', 'student_profile__school').get(pk=account.pk)

    def actors(self):
        return [self.fresh(account) for account in (
            self.counselor_a, self.org_a, self.teacher_a, self.counselor_b, self.org_b, self.solo,
            self.student_a.user, self.student_b.user, self.student_w.user,
        )]

    def rows(self, actor, path):
        self.client.force_authenticate(actor)
        response = self.client.get(path)
        if response.status_code == 403:
            return []
        self.assertEqual(response.status_code, 200, (actor.username, path, response.data))
        data = response.data
        return data.get('results', data) if isinstance(data, dict) else data


class CrossTenantProbeTests(CrossTenantFixture, APITestCase):
    def assert_tenant_sealed(self):
        """Nothing any school actor can read belongs to another tenant."""
        for actor in self.actors():
            tenant = tenant_school_id(actor)
            label = actor.username
            students = StudentProfile.objects.filter(id__in=[row['id'] for row in self.rows(actor, '/api/students/')])
            self.assertEqual({profile.school_id for profile in students} - {tenant}, set(), label)
            accounts = User.objects.filter(id__in=[row['id'] for row in self.rows(actor, '/api/users/accounts/')])
            self.assertEqual({tenant_school_id(account) for account in accounts} - {tenant}, set(), label)
            contacts = User.objects.filter(
                id__in=[row['id'] for row in self.rows(actor, '/api/message-channels/contacts/')],
            ).select_related('student_profile')
            for contact in contacts:
                if contact.role == User.Role.PARENT:
                    self.assertTrue(ParentStudentLink.objects.filter(
                        parent=contact, status=ParentStudentLink.Status.ACTIVE, student__school_id=tenant,
                    ).exists(), (label, contact.username))
                else:
                    self.assertEqual(tenant_school_id(contact), tenant, (label, contact.username))
            channels = MessageChannel.objects.filter(
                id__in=[row['id'] for row in self.rows(actor, '/api/message-channels/')],
            )
            # Membership is no excuse: a group or community of another school
            # must be gone. Direct chats stay readable as history once archived.
            for channel in channels.exclude(kind=MessageChannel.Kind.DIRECT):
                self.assertTrue(channel.is_global or channel.school_id == tenant, (label, channel.name))
            bookings = Booking.objects.filter(id__in=[row['id'] for row in self.rows(actor, '/api/bookings/')])
            self.assertEqual({booking.student.school_id for booking in bookings} - {tenant}, set(), label)
            if actor.role != User.Role.STUDENT:
                messages = StudentMessage.objects.filter(
                    id__in=[row['id'] for row in self.rows(actor, '/api/student-messages/')],
                )
                self.assertEqual({message.student.school_id for message in messages} - {tenant}, set(), label)

    def assert_parent_rules(self):
        for parent in (self.fresh(self.parent), self.fresh(self.pending_parent)):
            self.assertIsNone(parent.school_id)
            contact_ids = {row['id'] for row in self.rows(parent, '/api/message-channels/contacts/')}
            expected = set(StudentProfile.objects.filter(
                parent_links__parent=parent, parent_links__status=ParentStudentLink.Status.ACTIVE,
                assigned_counselor__isnull=False,
            ).values_list('assigned_counselor_id', flat=True))
            self.assertEqual(contact_ids, expected, parent.username)
            self.assertEqual({row['id'] for row in self.rows(parent, '/api/users/accounts/')}, {parent.id})
            self.assertEqual(self.rows(parent, '/api/students/'), [])
            self.client.force_authenticate(parent)
            for target in (self.student_a.user, self.teacher_a, self.org_b):
                response = self.client.post('/api/message-channels/direct/', {'user': target.id}, format='json')
                self.assertEqual(response.status_code, 403, (parent.username, target.username))
            self.assertEqual(self.client.post(f'/api/message-channels/{self.global_room.id}/join/').status_code, 404)
            created = self.client.post('/api/message-channels/', {'kind': 'discussion', 'name': 'x'}, format='json')
            self.assertEqual(created.status_code, 403)
            self.assertEqual(self.client.get('/api/parent-portal/').status_code, 200)

    def assert_old_school_locked_out(self, profile, old_staff):
        for staff in old_staff:
            self.client.force_authenticate(self.fresh(staff))
            self.assertEqual(self.client.get(f'/api/students/{profile.id}/').status_code, 404, staff.username)
            self.assertEqual(self.client.get(f'/api/users/accounts/{profile.user_id}/').status_code, 404)
            self.assertEqual(
                self.client.post(f'/api/users/accounts/{profile.user_id}/temporary-credential/', {}).status_code, 404,
            )

    # -- the probe ----------------------------------------------------------

    def test_tenants_stay_sealed_through_moves_transfers_and_parent_changes(self):
        self.assert_tenant_sealed()
        self.assert_parent_rules()

        # 1. A student moves from school A to school B.
        self.client.force_authenticate(self.admin)
        moved = self.client.patch(f'/api/students/{self.student_a.id}/', {'school': self.school_b.id}, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.user.school_id, self.school_b.id)
        self.assertIsNone(self.student_a.assigned_counselor_id)
        self.assertFalse(ChannelMembership.objects.filter(channel=self.group_a, user=self.student_a.user).exists())
        self.assertTrue(MessageChannel.objects.get(pk=self.parent_chat).is_archived)
        self.assert_old_school_locked_out(self.student_a, (self.counselor_a, self.org_a, self.teacher_a))
        self.assert_tenant_sealed()
        self.assert_parent_rules()

        # 2. The new school's counselor takes the student over; the parent
        #    reaches only that counselor.
        self.client.force_authenticate(self.fresh(self.counselor_b))
        assigned = self.client.post('/api/students/assign-counselor/', {'students': [self.student_a.id]}, format='json')
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.assert_parent_rules()
        self.assertEqual(
            {row['id'] for row in self.rows(self.fresh(self.parent), '/api/message-channels/contacts/')},
            {self.counselor_b.id},
        )

        # 3. School A's counselor transfers to school B.
        self.client.force_authenticate(self.admin)
        transferred = self.client.post(
            f'/api/users/accounts/{self.counselor_a.id}/transfer-school/', {'school': self.school_b.id}, format='json',
        )
        self.assertEqual(transferred.status_code, 200, transferred.data)
        self.assertFalse(ChannelMembership.objects.filter(channel=self.group_a, user=self.counselor_a).exists())
        self.assert_tenant_sealed()

        # 4. A student moves into the individual workspace and back out.
        for school in (self.workspace, self.school_a):
            self.client.force_authenticate(self.admin)
            response = self.client.patch(
                f'/api/users/accounts/{self.student_b.user_id}/', {'school': school.id}, format='json',
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assert_tenant_sealed()
        self.assert_old_school_locked_out(self.student_b, (self.counselor_b, self.org_b))

        # 5. The pending parent accepts, then the link is revoked.
        link = ParentStudentLink.objects.get(parent=self.pending_parent)
        self.client.force_authenticate(self.pending_parent)
        self.assertEqual(self.client.post(f'/api/parent-links/{link.id}/accept/').status_code, 200)
        self.assert_parent_rules()
        self.assertEqual(self.client.post(f'/api/parent-links/{link.id}/revoke/').status_code, 200)
        self.assert_parent_rules()
        self.assert_tenant_sealed()


MISSING_ID = 987654321

# basename -> model of a per-student record that has a detail endpoint.
STUDENT_RECORD_ENDPOINTS = {
    'applications': Application,
    'tasks': Task,
    'documents': Document,
    'achievements': Achievement,
    'researches': Research,
    'projects': Project,
    'internships': Internship,
    'activities': Activity,
    'honors': Honor,
    'recommendations': RecommendationLetter,
    'essays': Essay,
    'meetings': MeetingNote,
    'notifications': Notification,
    'activity': ActivityLog,
    'roadmap-missions': RoadmapMission,
    'program-services': ProgramService,
    'challenge-attempts': ChallengeAttempt,
    'bookings': Booking,
    'student-messages': StudentMessage,
    'parent-links': ParentStudentLink,
}
FILE_ENDPOINTS = (
    ('documents', 'file'),
    ('tasks', 'submission-file'),
    ('recommendations', 'file'),
    ('achievements', 'proof-file'),
    ('activities', 'proof-file'),
    ('honors', 'proof-file'),
)
# Search type -> model, for the student-owned result types.
SEARCH_MODELS = {
    'tasks': Task,
    'applications': Application,
    'documents': Document,
    'essays': Essay,
    'recommendations': RecommendationLetter,
    'roadmapMissions': RoadmapMission,
    'bookings': Booking,
}


class CrossTenantEndpointSweepTests(CrossTenantFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.university = University.objects.create(name='Probe University', country='United States')
        self.records = {}
        for profile in (self.student_a, self.student_b, self.student_w):
            self.records[profile.pk] = self.make_records(profile)
        self.profiles = {profile.pk: profile for profile in (self.student_a, self.student_b, self.student_w)}

    def make_records(self, profile):
        counselor = profile.assigned_counselor
        student = {'student': profile}
        application = Application.objects.create(**student, university=self.university, program='Probe program')
        mission = RoadmapMission.objects.create(**student, title='Probe mission', assigned_by=counselor)
        folder = EssayFolder.objects.create(**student, name='Probe folder')
        return {
            'applications': application,
            'tasks': Task.objects.create(
                **student, title='Probe task', due_date=timezone.localdate(), assigned_by=counselor,
            ),
            'documents': Document.objects.create(**student, title='Probe document'),
            'achievements': Achievement.objects.create(
                **student, title='Probe achievement', category='olympiad', description='Probe',
            ),
            'researches': Research.objects.create(**student, title='Probe research', summary='Probe'),
            'projects': Project.objects.create(**student, title='Probe project', description='Probe'),
            'internships': Internship.objects.create(**student, organization='Probe org', position='Intern'),
            'activities': Activity.objects.create(**student, name='Probe activity'),
            'honors': Honor.objects.create(**student, title='Probe honor'),
            'recommendations': RecommendationLetter.objects.create(**student, recommender_name='Probe recommender'),
            # Shared, so the sweep tests tenant scoping rather than the privacy filter.
            'essays': Essay.objects.create(
                **student, title='Probe essay', application=application, folder=folder, shared_with_counselor=True,
            ),
            'meetings': MeetingNote.objects.create(**student, title='Probe note', summary='Probe', counselor=counselor),
            'notifications': Notification.objects.create(**student, title='Probe', message='Probe'),
            'activity': ActivityLog.objects.create(actor=counselor, **student, action='Probe action'),
            'roadmap-missions': mission,
            'program-services': ProgramService.objects.create(
                **student, name='Probe service', mentor=counselor, unlimited=True,
            ),
            'challenge-attempts': ChallengeAttempt.objects.create(**student, challenge='riasec', answers={'1': 3}),
            'bookings': Booking.objects.filter(student=profile).first(),
            'student-messages': StudentMessage.objects.filter(student=profile).first(),
            'parent-links': ParentStudentLink.objects.filter(student=profile).first(),
            'folder': folder,
        }

    def all_actors(self):
        return [*self.actors(), self.fresh(self.parent), self.fresh(self.pending_parent)]

    def foreign_profiles(self, actor):
        tenant = tenant_school_id(actor)
        return [profile for profile in self.profiles.values() if tenant is None or profile.school_id != tenant]

    def status_of(self, actor, method, path, data=None):
        self.client.force_authenticate(actor)
        return getattr(self.client, method)(path, data or {}, format='json')

    # -- reads ----------------------------------------------------------------

    def test_lists_search_and_dashboards_show_only_the_callers_tenant(self):
        for actor in self.all_actors():
            tenant = tenant_school_id(actor)
            own_profile = getattr(actor, 'student_profile', None) if actor.role == User.Role.STUDENT else None

            def assert_students(student_ids, label):
                student_ids = {student_id for student_id in student_ids if student_id is not None}
                if own_profile is not None:
                    self.assertLessEqual(student_ids, {own_profile.pk}, label)
                    return
                schools = set(StudentProfile.objects.filter(pk__in=student_ids).values_list('school_id', flat=True))
                self.assertLessEqual(schools, {tenant} if tenant else set(), label)

            for basename in STUDENT_RECORD_ENDPOINTS:
                rows = self.rows(actor, f'/api/{basename}/')
                label = (actor.username, basename)
                if basename == 'parent-links' and actor.role == User.Role.PARENT:
                    self.assertEqual({row['parent'] for row in rows}, {actor.pk}, label)
                    continue
                assert_students([row['student'] for row in rows], label)

            screen_users = {row['user'] for row in self.rows(actor, '/api/screen-time/')}
            assert_students(
                StudentProfile.objects.filter(user_id__in=screen_users).values_list('pk', flat=True), actor.username,
            )
            self.assertLessEqual(
                {tenant_school_id(account) for account in User.objects.filter(pk__in=screen_users)} - {None},
                {tenant} if tenant else set(), actor.username,
            )
            schools = {row['id'] for row in self.rows(actor, '/api/schools/')}
            self.assertLessEqual(schools, {tenant} if tenant else set(), actor.username)
            roadmaps = self.rows(actor, '/api/counselor-roadmaps/')
            self.assertLessEqual({row['counselor'] for row in roadmaps}, {actor.pk}, actor.username)

            self.client.force_authenticate(actor)
            search = self.client.get('/api/search/', {'q': 'Probe'})
            self.assertEqual(search.status_code, 200, actor.username)
            for key, items in search.data['results'].items():
                ids = [item['id'] for item in items]
                if key == 'students':
                    assert_students(ids, (actor.username, key))
                elif key in SEARCH_MODELS:
                    students = SEARCH_MODELS[key].objects.filter(pk__in=ids).values_list('student_id', flat=True)
                    assert_students(students, (actor.username, key))
                else:
                    self.assertIn(key, {'supportTickets'}, actor.username)

            if actor.role != User.Role.PARENT:
                stats = self.client.get('/api/dashboard/stats/')
                self.assertEqual(stats.status_code, 200, actor.username)
                visible = StudentProfile.objects.filter(pk__in=[own_profile.pk] if own_profile else [
                    profile.pk for profile in self.profiles.values()
                    if profile.school_id == tenant and (
                        actor.role != User.Role.COUNSELOR or profile.assigned_counselor_id == actor.pk
                    )
                ])
                self.assertEqual(stats.data['students_total'], visible.count(), actor.username)
                if 'tasks_total' in stats.data:
                    self.assertEqual(
                        stats.data['tasks_total'], Task.objects.filter(student__in=visible).count(), actor.username,
                    )

    def test_another_tenants_ids_behave_like_missing_ids(self):
        for actor in self.all_actors():
            for profile in self.foreign_profiles(actor):
                records = self.records[profile.pk]
                probes = [f'/api/{basename}/{{}}/' for basename in STUDENT_RECORD_ENDPOINTS]
                probes += [f'/api/{basename}/{{}}/{suffix}/' for basename, suffix in FILE_ENDPOINTS]
                for template in probes:
                    basename = template.split('/')[2]
                    record = records[basename]
                    if record is None or getattr(record, 'parent_id', None) == actor.pk:
                        continue  # a parent's own invitation is theirs to read
                    missing = self.status_of(actor, 'get', template.format(MISSING_ID)).status_code
                    foreign = self.status_of(actor, 'get', template.format(record.pk)).status_code
                    self.assertIn(missing, {403, 404}, (actor.username, template))
                    self.assertEqual(foreign, missing, (actor.username, template, profile.user.username))
                for template in (
                    '/api/students/{}/', '/api/students/{}/photo/', '/api/students/{}/xp-history/',
                    '/api/students/{}/data-visibility/',
                ):
                    missing = self.status_of(actor, 'get', template.format(MISSING_ID)).status_code
                    foreign = self.status_of(actor, 'get', template.format(profile.pk)).status_code
                    self.assertIn(missing, {403, 404}, (actor.username, template))
                    self.assertEqual(foreign, missing, (actor.username, template))
                for template in ('/api/users/accounts/{}/', '/api/users/accounts/{}/avatar/'):
                    missing = self.status_of(actor, 'get', template.format(MISSING_ID)).status_code
                    foreign = self.status_of(actor, 'get', template.format(profile.user_id)).status_code
                    self.assertEqual(foreign, missing, (actor.username, template))
                if actor.role == User.Role.STUDENT:
                    for template in ('/api/essay-lab/essays/{}/', '/api/essay-lab/folders/{}/'):
                        record = records['essays' if 'essays' in template else 'folder']
                        missing = self.status_of(actor, 'get', template.format(MISSING_ID)).status_code
                        foreign = self.status_of(actor, 'get', template.format(record.pk)).status_code
                        self.assertEqual(foreign, missing, (actor.username, template))

    def test_writes_to_another_tenants_records_change_nothing(self):
        for actor in self.all_actors():
            for profile in self.foreign_profiles(actor):
                for basename, model in STUDENT_RECORD_ENDPOINTS.items():
                    record = self.records[profile.pk][basename]
                    if record is None or getattr(record, 'parent_id', None) == actor.pk:
                        continue
                    before = model.objects.filter(pk=record.pk).values().first()
                    for method in ('patch', 'delete'):
                        missing = self.status_of(actor, method, f'/api/{basename}/{MISSING_ID}/', {'title': 'x'})
                        foreign = self.status_of(actor, method, f'/api/{basename}/{record.pk}/', {'title': 'x'})
                        self.assertEqual(
                            foreign.status_code, missing.status_code, (actor.username, method, basename),
                        )
                    self.assertEqual(model.objects.filter(pk=record.pk).values().first(), before, basename)

    # -- ids in request bodies --------------------------------------------------

    def assert_foreign_like_missing(self, actor, method, path, payload, field, foreign_id, count=None):
        """``field=foreign_id`` must fail exactly like an id that does not exist."""
        before = count() if count else None
        missing_id = [MISSING_ID] if isinstance(foreign_id, list) else MISSING_ID
        missing = self.status_of(actor, method, path, {**payload, field: missing_id})
        foreign = self.status_of(actor, method, path, {**payload, field: foreign_id})
        label = (actor.username, method, path, field)
        self.assertGreaterEqual(missing.status_code, 400, label)
        self.assertEqual(foreign.status_code, missing.status_code, (label, foreign.data))
        # Messages may echo the id sent; apart from that they must be identical.
        self.assertEqual(
            str(foreign.data).replace(str(foreign_id), '<id>'), str(missing.data).replace(str(missing_id), '<id>'),
            label,
        )
        if count:
            self.assertEqual(count(), before, label)

    def create_payloads(self):
        return {
            'tasks': {'title': 'Probe', 'due_date': '2030-01-01'},
            'applications': {'program': 'Probe', 'university': self.university.pk},
            'documents': {'title': 'Probe', 'google_docs_url': 'https://docs.google.com/document/d/probe/edit'},
            'achievements': {'title': 'Probe', 'category': 'olympiad', 'description': 'Probe'},
            'researches': {'title': 'Probe', 'summary': 'Probe'},
            'projects': {'title': 'Probe', 'description': 'Probe'},
            'internships': {'organization': 'Probe', 'position': 'Intern'},
            'activities': {'name': 'Probe'},
            'honors': {'title': 'Probe'},
            'recommendations': {'recommender_name': 'Probe'},
            'essays': {'title': 'Probe'},
            'meetings': {'title': 'Probe', 'summary': 'Probe'},
            'notifications': {'title': 'Probe', 'message': 'Probe'},
            'roadmap-missions': {'title': 'Probe'},
            'program-services': {'name': 'Probe', 'unlimited': True},
        }

    def test_student_ids_in_request_bodies_stay_inside_the_callers_scope(self):
        payloads = self.create_payloads()
        writers = {
            self.fresh(self.counselor_a): list(payloads),
            self.fresh(self.solo): list(payloads),
            self.fresh(self.teacher_a): ['tasks', 'roadmap-missions'],
            self.fresh(self.student_a.user): [
                'tasks', 'applications', 'documents', 'achievements', 'researches', 'projects', 'internships',
                'activities', 'honors', 'recommendations', 'essays',
            ],
        }
        for actor, basenames in writers.items():
            own = self.student_w if actor.pk == self.solo.pk else self.student_a
            for basename in basenames:
                model = STUDENT_RECORD_ENDPOINTS[basename]
                payload = payloads[basename]
                if basename == 'applications':
                    payload = {**payload, 'program': f'Probe {actor.username}'}
                # The caller's own student works, so a rejection below is about scope.
                allowed = self.status_of(actor, 'post', f'/api/{basename}/', {**payload, 'student': own.pk})
                self.assertEqual(allowed.status_code, 201, (actor.username, basename, allowed.data))
                for foreign in self.foreign_profiles(actor) if actor.role != User.Role.STUDENT else [
                    profile for profile in self.profiles.values() if profile.pk != own.pk
                ]:
                    self.assert_foreign_like_missing(
                        actor, 'post', f'/api/{basename}/', payload, 'student', foreign.pk,
                        count=model.objects.filter(student=foreign).count,
                    )
                    own_record = self.records[own.pk][basename]
                    self.assert_foreign_like_missing(
                        actor, 'patch', f'/api/{basename}/{own_record.pk}/', {}, 'student', foreign.pk,
                        count=model.objects.filter(student=foreign).count,
                    )

    def test_an_essay_links_only_an_application_in_scope(self):
        counselor = self.fresh(self.counselor_a)
        foreign = self.records[self.student_b.pk]['applications'].pk
        essay = self.records[self.student_a.pk]['essays']
        self.assert_foreign_like_missing(
            counselor, 'post', '/api/essays/', {'student': self.student_a.pk, 'title': 'Probe'}, 'application', foreign,
        )
        self.assert_foreign_like_missing(counselor, 'patch', f'/api/essays/{essay.pk}/', {}, 'application', foreign)

    def test_a_mission_prerequisite_must_be_in_scope(self):
        self.assert_foreign_like_missing(
            self.fresh(self.counselor_a), 'post', '/api/roadmap-missions/',
            {'student': self.student_a.pk, 'title': 'Probe'},
            'prerequisite', self.records[self.student_b.pk]['roadmap-missions'].pk,
        )

    def test_a_service_mentor_comes_from_the_callers_school(self):
        counselor = self.fresh(self.counselor_a)
        service = self.records[self.student_a.pk]['program-services']
        self.assert_foreign_like_missing(
            counselor, 'post', '/api/program-services/',
            {'student': self.student_a.pk, 'name': 'Probe', 'unlimited': True}, 'mentor', self.counselor_b.pk,
        )
        self.assert_foreign_like_missing(
            counselor, 'patch', f'/api/program-services/{service.pk}/', {}, 'mentor', self.counselor_b.pk,
        )
        service.refresh_from_db()
        self.assertEqual(service.mentor_id, self.counselor_a.pk)

    def test_a_meeting_note_author_is_never_a_body_field(self):
        note = self.records[self.student_a.pk]['meetings']
        response = self.status_of(
            self.fresh(self.counselor_a), 'patch', f'/api/meetings/{note.pk}/', {'counselor': self.counselor_b.pk},
        )
        self.assertEqual(response.status_code, 200, response.data)
        note.refresh_from_db()
        self.assertEqual(note.counselor_id, self.counselor_a.pk)

    def test_a_student_books_and_files_only_inside_their_own_scope(self):
        student = self.fresh(self.student_a.user)
        own = self.records[self.student_a.pk]
        foreign_folder = self.records[self.student_b.pk]['folder'].pk
        self.assert_foreign_like_missing(
            student, 'post', '/api/bookings/',
            {'topic': 'Probe', 'starts_at': (timezone.now() + timedelta(days=2)).isoformat()},
            'participant', self.counselor_b.pk, count=Booking.objects.filter(participant=self.counselor_b).count,
        )
        self.assert_foreign_like_missing(
            student, 'post', '/api/essay-lab/essays/', {'title': 'Probe'}, 'folder', foreign_folder,
        )
        self.assert_foreign_like_missing(
            student, 'patch', f'/api/essay-lab/essays/{own["essays"].pk}/', {}, 'folder', foreign_folder,
        )

    def test_messages_post_only_into_the_callers_own_channels(self):
        teacher = self.fresh(self.teacher_a)
        foreign_room = MessageChannel.objects.get(school=self.school_b, kind=MessageChannel.Kind.COMMUNITY)
        foreign_message = ChannelMessage.objects.create(channel=foreign_room, sender=self.org_b, body='Probe')
        self.assert_foreign_like_missing(
            teacher, 'post', '/api/channel-messages/', {'body': 'Probe'}, 'channel', foreign_room.pk,
            count=foreign_room.messages.count,
        )
        self.assert_foreign_like_missing(
            teacher, 'post', '/api/channel-messages/', {'body': 'Probe', 'channel': self.group_a.pk},
            'parent', foreign_message.pk, count=foreign_message.replies.count,
        )

    def test_id_driven_actions_stay_inside_the_callers_scope(self):
        counselor = self.fresh(self.counselor_a)
        for foreign in (self.student_b, self.student_w):
            self.assert_foreign_like_missing(
                counselor, 'post', '/api/students/assign-counselor/', {}, 'students', [foreign.pk],
            )
            self.assert_foreign_like_missing(
                counselor, 'post', '/api/roadmap-missions/extend-level-one/', {}, 'student', foreign.pk,
                count=RoadmapMission.objects.filter(student=foreign).count,
            )
            self.assert_foreign_like_missing(
                counselor, 'post', '/api/student-messages/', {'body': 'Probe'}, 'student', foreign.pk,
                count=StudentMessage.objects.filter(student=foreign).count,
            )
            self.assert_foreign_like_missing(
                counselor, 'post', '/api/parent-links/invite/',
                {'email': 'probe-parent-new@example.com', 'password': PASSWORD, 'relationship': 'mother'},
                'student', foreign.pk, count=ParentStudentLink.objects.filter(student=foreign).count,
            )
            self.assert_foreign_like_missing(
                counselor, 'post', '/api/message-channels/direct/', {}, 'user', foreign.user_id,
            )
        self.assert_foreign_like_missing(
            counselor, 'post', f'/api/message-channels/{self.group_a.pk}/members/', {}, 'user', self.org_b.pk,
            count=self.group_a.memberships.count,
        )

    # -- assistant ----------------------------------------------------------------

    def test_assistant_context_holds_only_the_callers_own_aggregates(self):
        for counselor, profile in ((self.counselor_a, self.student_a), (self.solo, self.student_w)):
            context = build_role_context(self.fresh(counselor))
            self.assertEqual(context['assigned_student_count'], 1)
            self.assertEqual(sum(context['task_status_counts'].values()), Task.objects.filter(student=profile).count())
            self.assertEqual(
                sum(context['application_status_counts'].values()),
                Application.objects.filter(student=profile).count(),
            )
            self.assertNotIn(self.student_b.user.username, str(context))
        student_context = build_role_context(self.fresh(self.student_a.user))
        self.assertEqual(
            sum(student_context['task_status_counts'].values()), Task.objects.filter(student=self.student_a).count(),
        )
        # Whatever the role, the aggregates follow the canonical student scope:
        # school staff count their own school, a parent counts nobody.
        for account, profiles in (
            (self.org_a, [self.student_a]), (self.teacher_a, [self.student_a]), (self.parent, []),
        ):
            context = build_role_context(self.fresh(account))
            self.assertEqual(context['assigned_student_count'], len(profiles), account.username)
            self.assertEqual(
                sum(context['task_status_counts'].values()), Task.objects.filter(student__in=profiles).count(),
            )
        for account in (self.org_a, self.teacher_a, self.parent):
            self.client.force_authenticate(self.fresh(account))
            response = self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': 'hi'}]},
                                        format='json')
            self.assertIn(response.status_code, {403, 503}, account.username)
