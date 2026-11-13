"""Isolation audit: two schools, each with a counselor and students.

Covers what the student frontend (and the counselor meetings, weekly hours and
Telegram endpoints) call, from three angles:

* a student of school A against another school's records (B) and against a
  classmate's records (same school, other student);
* a counselor of school A against school B and against a same-school student
  they are not assigned to;
* ids in request bodies (student, participant, availability slot, channel,
  members, school) and file downloads.

Rule everywhere: another tenant's id must behave exactly like an id that does
not exist (same status), and no list may contain it.
"""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User

from ..models import (
    Achievement, Activity, ActivityLog, Application, Booking, ChallengeAttempt, ChannelMembership,
    ChannelMessage, Document, Essay, EssayFolder, Honor, Internship, MeetingAvailability, MeetingNote,
    MessageChannel, Notification, ProgramService, Project, RecommendationLetter, Research, RoadmapMission,
    School, StudentMessage, StudentProfile, Task, University,
)

PASSWORD = 'StrongPass123!'
MISSING_ID = 987654321

RECORD_BASENAMES = (
    'applications', 'tasks', 'documents', 'achievements', 'researches', 'projects', 'internships', 'activities',
    'honors', 'recommendations', 'essays', 'meetings', 'notifications', 'activity', 'roadmap-missions',
    'program-services', 'challenge-attempts', 'bookings', 'student-messages',
)
FILE_ENDPOINTS = (
    ('documents', 'file'), ('tasks', 'submission-file'), ('recommendations', 'file'),
    ('achievements', 'proof-file'), ('activities', 'proof-file'), ('honors', 'proof-file'),
)


class IsolationFixture:
    """School A: counselor_a (students a1, a2), counselor_a2 (student a3), teacher_a. School B: counselor_b (b1)."""

    def setUp(self):
        self.school_a = School.objects.create(name='Audit A', code='audit-a')
        self.school_b = School.objects.create(name='Audit B', code='audit-b')
        self.counselor_a = self.user('audit-counselor-a', User.Role.COUNSELOR, self.school_a)
        self.counselor_a2 = self.user('audit-counselor-a2', User.Role.COUNSELOR, self.school_a)
        self.teacher_a = self.user('audit-teacher-a', User.Role.TEACHER, self.school_a)
        self.org_a = self.user('audit-org-a', User.Role.ORGANIZATION, self.school_a)
        self.counselor_b = self.user('audit-counselor-b', User.Role.COUNSELOR, self.school_b)
        self.teacher_b = self.user('audit-teacher-b', User.Role.TEACHER, self.school_b)
        self.a1 = self.student('audit-a1', self.school_a, self.counselor_a)
        self.a2 = self.student('audit-a2', self.school_a, self.counselor_a)
        self.a3 = self.student('audit-a3', self.school_a, self.counselor_a2)
        self.b1 = self.student('audit-b1', self.school_b, self.counselor_b)
        self.university = University.objects.create(name='Audit University', country='United States')
        self.records = {p.pk: self.make_records(p) for p in (self.a1, self.a2, self.a3, self.b1)}

    def user(self, username, role, school):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password=PASSWORD, role=role, school=school,
        )

    def student(self, username, school, counselor):
        account = self.user(username, User.Role.STUDENT, school)
        return StudentProfile.objects.create(
            user=account, school=school, school_name=school.name, assigned_counselor=counselor,
        )

    def make_records(self, profile):
        counselor = profile.assigned_counselor
        student = {'student': profile}
        application = Application.objects.create(**student, university=self.university, program='Audit program')
        folder = EssayFolder.objects.create(**student, name='Audit folder')
        Booking.objects.create(
            student=profile, participant=counselor, topic='Audit meeting', starts_at=timezone.now() + timedelta(days=3),
        )
        StudentMessage.objects.create(student=profile, sender=counselor, recipient=profile.user, body='Audit')
        return {
            'applications': application,
            'tasks': Task.objects.create(**student, title='Audit task', due_date=timezone.localdate(), assigned_by=counselor),
            'documents': Document.objects.create(**student, title='Audit document'),
            'achievements': Achievement.objects.create(**student, title='Audit', category='olympiad', description='x'),
            'researches': Research.objects.create(**student, title='Audit research', summary='x'),
            'projects': Project.objects.create(**student, title='Audit project', description='x'),
            'internships': Internship.objects.create(**student, organization='Audit org', position='Intern'),
            'activities': Activity.objects.create(**student, name='Audit activity'),
            'honors': Honor.objects.create(**student, title='Audit honor'),
            'recommendations': RecommendationLetter.objects.create(**student, recommender_name='Audit rec'),
            'essays': Essay.objects.create(
                **student, title='Audit essay', application=application, folder=folder, shared_with_counselor=True,
            ),
            'meetings': MeetingNote.objects.create(**student, title='Audit note', summary='x', counselor=counselor),
            'notifications': Notification.objects.create(**student, title='Audit', message='Audit'),
            'activity': ActivityLog.objects.create(actor=counselor, **student, action='Audit action'),
            'roadmap-missions': RoadmapMission.objects.create(**student, title='Audit mission', assigned_by=counselor),
            'program-services': ProgramService.objects.create(**student, name='Audit service', mentor=counselor, unlimited=True),
            'challenge-attempts': ChallengeAttempt.objects.create(**student, challenge='riasec', answers={'1': 3}),
            'bookings': Booking.objects.filter(student=profile).first(),
            'student-messages': StudentMessage.objects.filter(student=profile).first(),
            'folder': folder,
        }

    def call(self, actor, method, path, data=None, **extra):
        self.client.force_authenticate(actor)
        return getattr(self.client, method)(path, data or {}, format='json', **extra)

    def ids(self, actor, path):
        response = self.call(actor, 'get', path)
        if response.status_code in (403, 404):
            return set()
        self.assertEqual(response.status_code, 200, (actor.username, path, response.data))
        data = response.data
        rows = data.get('results', data) if isinstance(data, dict) else data
        return {row['id'] for row in rows if isinstance(row, dict) and 'id' in row}


class RecordIsolationTests(IsolationFixture, APITestCase):
    """Student endpoints: a classmate's and another school's records are unreachable."""

    def foreign_for(self, actor_profile):
        return [p for p in (self.a1, self.a2, self.a3, self.b1) if p.pk != actor_profile.pk]

    def assert_like_missing(self, actor, method, template, record, label, payload=None):
        missing = self.call(actor, method, template.format(MISSING_ID), payload)
        foreign = self.call(actor, method, template.format(record.pk), payload)
        self.assertEqual(foreign.status_code, missing.status_code, (label, method, template, foreign.data))

    def run_record_sweep(self, actor, foreign_profiles):
        for profile in foreign_profiles:
            for basename in RECORD_BASENAMES:
                record = self.records[profile.pk][basename]
                listed = self.ids(actor, f'/api/{basename}/')
                self.assertNotIn(record.pk, listed, (actor.username, basename, 'listed'))
                for method in ('get', 'patch', 'delete'):
                    self.assert_like_missing(
                        actor, method, f'/api/{basename}/{{}}/', record, (actor.username, profile.user.username),
                        {'title': 'x'} if method == 'patch' else None,
                    )
            for basename, suffix in FILE_ENDPOINTS:
                record = self.records[profile.pk][basename]
                self.assert_like_missing(actor, 'get', f'/api/{basename}/{{}}/{suffix}/', record, actor.username)
            for template in (
                '/api/students/{}/', '/api/students/{}/photo/', '/api/students/{}/cv/', '/api/students/{}/xp-history/',
                '/api/students/{}/data-visibility/',
            ):
                missing = self.call(actor, 'get', template.format(MISSING_ID)).status_code
                foreign = self.call(actor, 'get', template.format(profile.pk)).status_code
                self.assertEqual(foreign, missing, (actor.username, template))
            for template in ('/api/essay-lab/essays/{}/', '/api/essay-lab/folders/{}/'):
                record = self.records[profile.pk]['essays' if 'essays' in template else 'folder']
                missing = self.call(actor, 'get', template.format(MISSING_ID)).status_code
                foreign = self.call(actor, 'get', template.format(record.pk)).status_code
                self.assertEqual(foreign, missing, (actor.username, template))
        students = self.ids(actor, '/api/students/')
        for profile in foreign_profiles:
            self.assertNotIn(profile.pk, students, (actor.username, 'students list'))

    def test_student_cannot_reach_classmate_or_other_school_records(self):
        self.run_record_sweep(self.a1.user, self.foreign_for(self.a1))

    def test_counselor_cannot_reach_unassigned_same_school_or_other_school_records(self):
        self.run_record_sweep(self.counselor_a, [self.a3, self.b1])

    def test_other_school_counselor_cannot_reach_school_a(self):
        self.run_record_sweep(self.counselor_b, [self.a1, self.a2, self.a3])

    def test_teacher_and_organization_stay_in_their_school(self):
        self.run_record_sweep(self.teacher_b, [self.a1, self.a2, self.a3])
        self.run_record_sweep(self.teacher_a, [self.b1])
        self.run_record_sweep(self.org_a, [self.b1])

    def test_student_cannot_create_records_for_another_student(self):
        payloads = {
            'tasks': {'title': 'Probe', 'due_date': '2030-01-01'},
            'applications': {'program': 'Probe', 'university': self.university.pk},
            'documents': {'title': 'Probe', 'google_docs_url': 'https://docs.google.com/document/d/probe/edit'},
            'achievements': {'title': 'Probe', 'category': 'olympiad', 'description': 'x'},
            'activities': {'name': 'Probe'},
            'essays': {'title': 'Probe'},
            'roadmap-missions': {'title': 'Probe'},
            'program-services': {'name': 'Probe', 'unlimited': True},
        }
        models = {
            'tasks': Task, 'applications': Application, 'documents': Document, 'achievements': Achievement,
            'activities': Activity, 'essays': Essay, 'roadmap-missions': RoadmapMission,
            'program-services': ProgramService,
        }
        for actor, victims in ((self.a1.user, (self.a2, self.b1)), (self.counselor_a, (self.a3, self.b1))):
            for victim in victims:
                for basename, payload in payloads.items():
                    before = models[basename].objects.filter(student=victim).count()
                    self.call(actor, 'post', f'/api/{basename}/', {**payload, 'student': victim.pk})
                    self.assertEqual(
                        models[basename].objects.filter(student=victim).count(), before,
                        (actor.username, basename, victim.user.username),
                    )

    def test_foreign_application_cannot_be_linked_to_own_essay(self):
        foreign = self.records[self.b1.pk]['applications']
        mine = Essay.objects.create(student=self.a1, title='Mine')
        response = self.call(self.a1.user, 'patch', f'/api/essays/{mine.pk}/', {'application': foreign.pk})
        self.assertGreaterEqual(response.status_code, 400)
        mine.refresh_from_db()
        self.assertIsNone(mine.application_id)

    def test_private_essay_hidden_from_counselor_until_shared(self):
        private = Essay.objects.create(student=self.a1, title='Private', shared_with_counselor=False)
        self.assertNotIn(private.pk, self.ids(self.counselor_a, '/api/essays/'))
        self.assertEqual(self.call(self.counselor_a, 'get', f'/api/essays/{private.pk}/').status_code, 404)
        self.assertEqual(self.call(self.counselor_a, 'get', f'/api/essay-lab/review/essays/{private.pk}/').status_code, 404)

    def test_file_downloads_are_scoped(self):
        document = self.records[self.b1.pk]['documents']
        document.file.save('secret.pdf', SimpleUploadedFile('secret.pdf', b'%PDF-1.4 secret'), save=True)
        for actor in (self.a1.user, self.a2.user, self.counselor_a, self.teacher_a, self.counselor_a2):
            response = self.call(actor, 'get', f'/api/documents/{document.pk}/file/')
            self.assertIn(response.status_code, (403, 404), actor.username)
        owner = self.call(self.b1.user, 'get', f'/api/documents/{document.pk}/file/')
        self.assertEqual(owner.status_code, 200)
        self.assertEqual(self.call(self.counselor_b, 'get', f'/api/documents/{document.pk}/file/').status_code, 200)


class NotificationScopeTests(IsolationFixture, APITestCase):
    """Bell counts and read-all are per user, never per school."""

    def test_summary_and_read_all_touch_only_the_callers_notices(self):
        for profile in (self.a1, self.a2, self.b1):
            Notification.objects.create(student=profile, title='Bell', message='x')
        before = Notification.objects.filter(student=self.a2, is_read=False).count()
        summary = self.call(self.a1.user, 'get', '/api/notifications/summary/').data
        own_unread = Notification.objects.filter(student=self.a1, recipient__isnull=True, is_read=False).count()
        self.assertEqual(summary['unread'], own_unread)
        self.call(self.a1.user, 'post', '/api/notifications/read-all/')
        self.assertEqual(Notification.objects.filter(student=self.a2, is_read=False).count(), before)
        self.assertEqual(Notification.objects.filter(student=self.b1, is_read=False).count(), 2)
        self.call(self.counselor_a, 'post', '/api/notifications/read-all/')
        self.assertTrue(Notification.objects.filter(student=self.a3, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(student=self.b1, is_read=False).exists())
        foreign = Notification.objects.create(student=self.a1, title='Fresh', message='x')
        self.assertEqual(self.call(self.counselor_b, 'post', f'/api/notifications/{foreign.pk}/read/').status_code, 404)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)

    def test_student_cannot_mark_another_students_notice_read(self):
        note = Notification.objects.filter(student=self.a2).first()
        response = self.call(self.a1.user, 'post', f'/api/notifications/{note.pk}/read/')
        self.assertEqual(response.status_code, 404)
        note.refresh_from_db()
        self.assertFalse(note.is_read)

    def test_student_cannot_forge_notifications(self):
        response = self.call(self.a1.user, 'post', '/api/notifications/', {'student': self.a2.pk, 'title': 'x', 'message': 'x'})
        self.assertIn(response.status_code, (400, 403))


@override_settings(TELEGRAM_BOT_USERNAME='audit_bot')
class BookingScopeTests(IsolationFixture, APITestCase):
    """Booking slots, weekly hours and meeting participants never cross a school."""

    def setUp(self):
        super().setUp()
        start = (timezone.now() + timedelta(days=5)).replace(minute=0, second=0, microsecond=0)
        self.slot_a = MeetingAvailability.objects.create(participant=self.counselor_a, starts_at=start)
        self.slot_b = MeetingAvailability.objects.create(participant=self.counselor_b, starts_at=start + timedelta(hours=2))
        self.slot_a2 = MeetingAvailability.objects.create(participant=self.counselor_a2, starts_at=start + timedelta(hours=4))
        from apps.telegram_bot.models import StudentTelegram

        for n, profile in enumerate((self.a1, self.b1), start=1):
            StudentTelegram.objects.create(user=profile.user, chat_id=1000 + n)

    def book(self, actor, participant, slot):
        return self.call(actor, 'post', '/api/bookings/', {
            'participant': participant.pk, 'availability_slot': slot.pk, 'starts_at': slot.starts_at.isoformat(),
            'duration_minutes': slot.duration_minutes, 'topic': 'Audit booking',
        })

    def test_student_books_only_own_school_staff_slots(self):
        for participant, slot in ((self.counselor_b, self.slot_b), (self.counselor_a, self.slot_b), (self.counselor_b, self.slot_a)):
            response = self.book(self.a1.user, participant, slot)
            self.assertEqual(response.status_code, 400, (participant.username, slot.pk, response.data))
        self.assertFalse(Booking.objects.filter(topic='Audit booking').exists())
        self.assertEqual(self.book(self.b1.user, self.counselor_a, self.slot_a).status_code, 400)
        ok = self.book(self.a1.user, self.counselor_a, self.slot_a)
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_participant_and_slot_listings_exclude_other_schools(self):
        participants = self.ids(self.a1.user, '/api/bookings/participants/')
        self.assertIn(self.counselor_a.pk, participants)
        self.assertNotIn(self.counselor_b.pk, participants)
        self.assertNotIn(self.teacher_b.pk, participants)
        slots = self.call(self.a1.user, 'get', '/api/bookings/availability/').data
        self.assertNotIn(self.slot_b.pk, {row['id'] for row in slots})
        self.assertEqual(
            self.call(self.a1.user, 'get', f'/api/bookings/availability/?participant={self.counselor_b.pk}').status_code, 400,
        )

    def test_student_cannot_reschedule_onto_another_schools_slot(self):
        booking = Booking.objects.create(
            student=self.a1, participant=self.counselor_a, topic='Mine', status=Booking.Status.PENDING,
            starts_at=timezone.now() + timedelta(days=9), availability_slot=None,
        )
        response = self.call(self.a1.user, 'post', f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': self.slot_b.starts_at.isoformat(), 'availability_slot': self.slot_b.pk,
        })
        self.assertGreaterEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertNotEqual(booking.starts_at, self.slot_b.starts_at)

    def test_other_schools_bookings_are_untouchable(self):
        target = self.records[self.b1.pk]['bookings']
        for actor in (self.counselor_a, self.a1.user, self.teacher_a):
            for action in ('approve', 'reject', 'complete', 'cancel', 'reschedule'):
                response = self.call(actor, 'post', f'/api/bookings/{target.pk}/{action}/', {
                    'starts_at': (timezone.now() + timedelta(days=30)).isoformat(),
                })
                self.assertIn(response.status_code, (403, 404), (actor.username, action))
        target.refresh_from_db()
        self.assertEqual(target.status, Booking.Status.PENDING)

    def test_staff_cannot_book_or_edit_slots_of_another_school(self):
        response = self.call(self.counselor_a, 'post', '/api/bookings/', {
            'student': self.b1.pk, 'topic': 'x', 'starts_at': (timezone.now() + timedelta(days=20)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)
        # a classmate assigned to another counselor is not "my student" either
        response = self.call(self.counselor_a, 'post', '/api/bookings/', {
            'student': self.a3.pk, 'topic': 'x', 'starts_at': (timezone.now() + timedelta(days=21)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.call(self.counselor_a, 'delete', '/api/bookings/availability/', {'id': self.slot_b.pk}).status_code, 404)
        self.assertEqual(self.call(self.counselor_a, 'patch', '/api/bookings/availability/', {
            'id': self.slot_b.pk, 'starts_at': (timezone.now() + timedelta(days=40)).isoformat(),
        }).status_code, 404)
        self.assertEqual(self.call(self.counselor_a, 'get', f'/api/bookings/availability/?reschedule={self.records[self.b1.pk]["bookings"].pk}').status_code, 404)
        self.assertTrue(MeetingAvailability.objects.filter(pk=self.slot_b.pk).exists())
        # students cannot manage availability at all
        self.assertEqual(self.call(self.a1.user, 'post', '/api/bookings/availability/', {
            'starts_at': (timezone.now() + timedelta(days=22)).isoformat(),
        }).status_code, 403)

    def test_weekly_hours_belong_to_the_caller_only(self):
        hours = {'hours': {'0': [['09:00', '12:00']]}, 'duration_minutes': 45}
        self.assertEqual(self.call(self.counselor_b, 'put', '/api/bookings/availability/weekly/', hours).status_code, 200)
        a_view = self.call(self.counselor_a, 'get', '/api/bookings/availability/weekly/').data
        self.assertEqual(a_view.get('hours') or {}, {})
        self.assertEqual(self.call(self.a1.user, 'get', '/api/bookings/availability/weekly/').status_code, 403)
        self.assertEqual(self.call(self.a1.user, 'put', '/api/bookings/availability/weekly/', hours).status_code, 403)

    def test_meeting_notes_are_staff_only_and_scoped(self):
        self.assertEqual(self.call(self.a1.user, 'get', '/api/meetings/').status_code, 403)
        mine = self.ids(self.counselor_a, '/api/meetings/')
        self.assertEqual(mine, {self.records[self.a1.pk]['meetings'].pk, self.records[self.a2.pk]['meetings'].pk})
        response = self.call(self.counselor_a, 'post', '/api/meetings/', {
            'student': self.b1.pk, 'title': 'x', 'summary': 'x',
        })
        self.assertGreaterEqual(response.status_code, 400)


class MessagingScopeTests(IsolationFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.public_b = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='B community', school=self.school_b, is_public=True,
        )
        ChannelMembership.objects.create(channel=self.public_b, user=self.teacher_b, role=ChannelMembership.Role.OWNER)
        self.private_b = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='B group', school=self.school_b)
        for member in (self.teacher_b, self.b1.user):
            ChannelMembership.objects.create(channel=self.private_b, user=member)
        self.message_b = ChannelMessage.objects.create(channel=self.private_b, sender=self.b1.user, body='secret')
        self.message_b.attachment.save('a.pdf', SimpleUploadedFile('a.pdf', b'%PDF-1.4 x'), save=True)

    def test_direct_channels_open_only_inside_the_school(self):
        for target in (self.b1.user, self.counselor_b, self.teacher_b):
            self.assertEqual(self.call(self.a1.user, 'post', '/api/message-channels/direct/', {'user': target.pk}).status_code, 403, target.username)
        for target in (self.a2.user, self.a3.user):  # classmates are not contacts for a student
            self.assertEqual(self.call(self.a1.user, 'post', '/api/message-channels/direct/', {'user': target.pk}).status_code, 403, target.username)
        self.assertEqual(self.call(self.counselor_a, 'post', '/api/message-channels/direct/', {'user': self.b1.user.pk}).status_code, 403)
        self.assertEqual(self.call(self.counselor_a, 'post', '/api/message-channels/direct/', {'user': self.a3.user.pk}).status_code, 403)
        self.assertEqual(self.call(self.counselor_a, 'post', '/api/message-channels/direct/', {'user': self.counselor_b.pk}).status_code, 403)
        self.assertEqual(self.call(self.a1.user, 'post', '/api/message-channels/direct/', {'user': self.counselor_a.pk}).status_code, 201)

    def test_contacts_exclude_other_schools(self):
        for actor in (self.a1.user, self.counselor_a, self.teacher_a):
            contacts = self.ids(actor, '/api/message-channels/contacts/')
            self.assertFalse(contacts & {self.b1.user.pk, self.counselor_b.pk, self.teacher_b.pk}, actor.username)
        self.assertNotIn(self.a2.user.pk, self.ids(self.a1.user, '/api/message-channels/contacts/'))
        self.assertNotIn(self.a3.user.pk, self.ids(self.counselor_a, '/api/message-channels/contacts/'))

    def test_foreign_channels_are_invisible_and_unwritable(self):
        for actor in (self.a1.user, self.counselor_a, self.teacher_a):
            listed = self.ids(actor, '/api/message-channels/')
            self.assertFalse(listed & {self.public_b.pk, self.private_b.pk}, actor.username)
            for channel in (self.public_b, self.private_b):
                self.assertEqual(self.call(actor, 'get', f'/api/message-channels/{channel.pk}/').status_code, 404)
                self.assertEqual(self.call(actor, 'post', f'/api/message-channels/{channel.pk}/join/').status_code, 404)
                self.assertEqual(self.call(actor, 'get', f'/api/message-channels/{channel.pk}/members/').status_code, 404)
                self.assertEqual(self.call(actor, 'get', f'/api/channel-messages/?channel={channel.pk}').data.get('results', []), [])
                post = self.call(actor, 'post', '/api/channel-messages/', {'channel': channel.pk, 'body': 'hi'})
                self.assertEqual(post.status_code, 400, (actor.username, post.data))
            self.assertEqual(self.call(actor, 'get', f'/api/channel-messages/{self.message_b.pk}/').status_code, 404)
            self.assertEqual(self.call(actor, 'get', f'/api/channel-messages/{self.message_b.pk}/attachment/').status_code, 404)
            self.assertEqual(self.call(actor, 'post', f'/api/channel-messages/{self.message_b.pk}/report/', {'reason': 'spam'}).status_code, 404)
        self.assertFalse(ChannelMessage.objects.filter(body='hi').exists())

    def test_channel_creation_and_membership_stay_in_the_school(self):
        created = self.call(self.teacher_a, 'post', '/api/message-channels/', {
            'kind': 'group', 'name': 'x', 'school': self.school_b.pk, 'members': [self.b1.user.pk, self.a1.user.pk, self.counselor_b.pk],
        })
        self.assertIn(created.status_code, (201, 400), created.data)
        if created.status_code == 201:
            channel = MessageChannel.objects.get(pk=created.data['id'])
            self.assertEqual(channel.school_id, self.school_a.pk)
            members = set(channel.memberships.values_list('user_id', flat=True))
            self.assertFalse(members & {self.b1.user.pk, self.counselor_b.pk})
        own = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name='A group', school=self.school_a)
        ChannelMembership.objects.create(channel=own, user=self.teacher_a, role=ChannelMembership.Role.OWNER)
        for target in (self.b1.user, self.counselor_b, self.teacher_b):
            self.assertEqual(self.call(self.teacher_a, 'post', f'/api/message-channels/{own.pk}/members/', {'user': target.pk}).status_code, 403, target.username)
        self.assertEqual(self.call(self.a1.user, 'post', '/api/message-channels/', {'kind': 'group', 'name': 'x'}).status_code, 400)
        # a global channel can only be created by a product admin
        self.assertEqual(self.call(self.teacher_a, 'post', '/api/message-channels/', {
            'kind': 'community', 'name': 'x', 'is_global': True,
        }).status_code, 403)

    def test_legacy_student_messages_follow_the_scope(self):
        theirs = self.records[self.a2.pk]['student-messages']
        self.assertNotIn(theirs.pk, self.ids(self.a1.user, '/api/student-messages/'))
        response = self.call(self.a1.user, 'post', '/api/student-messages/', {'body': 'hi', 'student': self.b1.pk})
        if response.status_code == 201:
            message = StudentMessage.objects.get(pk=response.data['id'])
            self.assertEqual(message.student_id, self.a1.pk)
            self.assertEqual(message.recipient_id, self.counselor_a.pk)
        response = self.call(self.counselor_a, 'post', '/api/student-messages/', {'body': 'hi', 'student': self.a3.pk})
        self.assertEqual(response.status_code, 400)
        response = self.call(self.counselor_a, 'post', '/api/student-messages/', {'body': 'hi', 'student': self.b1.pk})
        self.assertEqual(response.status_code, 400)

    def test_student_team_lists_only_own_counselor_and_school_organization(self):
        response = self.call(self.a1.user, 'get', '/api/student-team/')
        self.assertEqual(response.status_code, 200)
        team_ids = {row['id'] for row in response.data}
        self.assertEqual(team_ids, {self.counselor_a.pk, self.org_a.pk})
        # A stale cross-school assignment (should never exist) still leaks nobody.
        StudentProfile.objects.filter(pk=self.a1.pk).update(assigned_counselor=self.counselor_b)
        fresh = User.objects.get(pk=self.a1.user.pk)
        team_ids = {row['id'] for row in self.call(fresh, 'get', '/api/student-team/').data}
        self.assertNotIn(self.counselor_b.pk, team_ids)

    def test_student_message_never_addressed_to_a_stale_cross_school_counselor(self):
        """Defence in depth: a stale cross-school assignment must not become a message recipient."""
        StudentProfile.objects.filter(pk=self.a1.pk).update(assigned_counselor=self.counselor_b)
        fresh = User.objects.get(pk=self.a1.user.pk)
        response = self.call(fresh, 'post', '/api/student-messages/', {'body': 'hello'})
        self.assertEqual(response.status_code, 400, response.data)

    def test_student_cannot_rewrite_counselors_message_in_own_thread(self):
        """Integrity: the student edits/deletes the counselor's message body in their own thread."""
        message = self.records[self.a1.pk]['student-messages']
        self.call(self.a1.user, 'patch', f'/api/student-messages/{message.pk}/', {'body': 'tampered'})
        message.refresh_from_db()
        self.assertNotEqual(message.body, 'tampered')
