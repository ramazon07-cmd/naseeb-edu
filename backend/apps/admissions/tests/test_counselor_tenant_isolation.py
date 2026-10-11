"""Counselor dashboard isolation: across schools (tenants) and across counselors of one school.

Two schools, two counselors each, two students per counselor, and a record of
every kind for every student. Every student's name and record titles carry a
unique token (``zqx<owner>s<n>x``), so a response leaks if its text holds a
token of a student outside the caller's scope, or a ``student`` id of one.

Failures are reported as ``REAL LEAK`` (foreign data read, or a foreign id
acted on with a 2xx) or ``UNEXPECTED STATUS`` (refused, but not as 403/404).
"""
import json
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import (
    Achievement,
    ActivityLog,
    Booking,
    ChannelMembership,
    ChannelMessage,
    Document,
    Essay,
    MeetingAvailability,
    MeetingNote,
    MessageChannel,
    Notification,
    RoadmapMission,
    School,
    StudentMessage,
    Task,
)
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.users.models import User

REFUSED = {403, 404}
# School-wide objects (a public community) carry their school's token: foreign only to the other school.
SCHOOL_TOKENS = {'a': 'zqxschoolax', 'b': 'zqxschoolbx'}


def token(owner, index):
    return f'zqx{owner}s{index}x'


class TenantIsolationFixture(AuditBaseMixin):
    """School A: counselors a1 (``self.counselor``) and a2 (``self.counselor_peer``).
    School B: counselors b1 (``self.counselor_b``) and b2. Two students each."""

    def setUp(self):
        super().setUp()
        self.counselor_b2 = self.make_user('iso-counselor-b2', User.Role.COUNSELOR, self.school_b)
        self.teacher_b = self.make_user('iso-teacher-b', User.Role.TEACHER, self.school_b)
        self.organization_b = self.make_user('iso-org-b', User.Role.ORGANIZATION, self.school_b)
        self.counselors = {
            'a1': self.counselor, 'a2': self.counselor_peer, 'b1': self.counselor_b, 'b2': self.counselor_b2,
        }
        schools = {'a1': self.school_a, 'a2': self.school_a, 'b1': self.school_b, 'b2': self.school_b}
        # The base mixin's two students become a1's and b1's first students.
        base = {'a1': self.student, 'b1': self.student_b}
        self.students = {}
        self.tokens = {}
        self.records = {}
        for owner, counselor in self.counselors.items():
            for index in range(2):
                tok = token(owner, index)
                if index == 0 and owner in base:
                    profile = base[owner]
                    User.objects.filter(pk=profile.user_id).update(first_name=tok, last_name='Student')
                else:
                    account = self.make_user(tok, User.Role.STUDENT, schools[owner], first_name=tok, last_name='Student')
                    profile = self.make_profile(account, schools[owner], counselor)
                profile.refresh_from_db()
                self.students[(owner, index)] = profile
                self.tokens[profile.pk] = tok
                self.records[profile.pk] = self.make_records(profile, counselor, tok)
        self.make_channels()
        self.slots = {
            owner: MeetingAvailability.objects.create(
                participant=counselor, starts_at=self.future(days=5, hours=i), duration_minutes=45,
            )
            for i, (owner, counselor) in enumerate(self.counselors.items())
        }

    @staticmethod
    def future(days=2, hours=0):
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        return base + timedelta(days=days, hours=10 + hours)

    def make_records(self, profile, counselor, tok):
        today = timezone.localdate()
        student = {'student': profile}
        records = {
            'tasks': Task.objects.create(
                **student, title=f'{tok} task', due_date=today, assigned_by=counselor,
                status=Task.Status.SUBMITTED, submitted_at=timezone.now(),
            ),
            'tasks_open': Task.objects.create(
                **student, title=f'{tok} open task', due_date=today + timedelta(days=2), assigned_by=counselor,
            ),
            'documents': Document.objects.create(**student, title=f'{tok} document', status=Document.Status.UPLOADED, google_docs_url='https://docs.google.com/document/d/x'),
            'achievements': Achievement.objects.create(
                **student, title=f'{tok} achievement', category='olympiad', description=tok,
            ),
            'roadmap-missions': RoadmapMission.objects.create(
                **student, title=f'{tok} mission', assigned_by=counselor, status=RoadmapMission.Status.SUBMITTED,
            ),
            'essays': Essay.objects.create(
                **student, title=f'{tok} essay', content=tok, status=Essay.Status.REVIEWING,
                shared_with_counselor=True, shared_at=timezone.now(),
            ),
            'meetings': MeetingNote.objects.create(**student, title=f'{tok} note', summary=tok, counselor=counselor),
            'notifications': Notification.objects.create(**student, title=f'{tok} notice', message=tok),
            'addressed': Notification.objects.create(
                **student, recipient=counselor, title=f'{tok} for counselor', message=tok,
                kind=Notification.Kind.MEETING,
            ),
            'activity': ActivityLog.objects.create(actor=counselor, **student, action=f'{tok} action'),
            'student-messages': StudentMessage.objects.create(
                student=profile, sender=counselor, recipient=profile.user, body=f'{tok} message',
            ),
            'bookings': Booking.objects.create(
                student=profile, participant=counselor, topic=f'{tok} meeting',
                starts_at=self.future(days=1, hours=len(self.records)), status=Booking.Status.PENDING,
            ),
        }
        return records

    def make_channels(self):
        self.channels = {}
        for owner, counselor in self.counselors.items():
            school = counselor.school
            tok = token(owner, 0)
            group = MessageChannel.objects.create(
                kind=MessageChannel.Kind.GROUP, name=f'{tok} group', school=school, created_by=counselor,
            )
            ChannelMembership.objects.create(channel=group, user=counselor, role=ChannelMembership.Role.OWNER)
            for index in range(2):
                ChannelMembership.objects.create(channel=group, user=self.students[(owner, index)].user)
            ChannelMessage.objects.create(channel=group, sender=counselor, body=f'{tok} group message')
            group.last_message_at = timezone.now()
            group.save(update_fields=['last_message_at'])
            self.channels[owner] = group
        # A public community in school B: school A must never discover it.
        self.community_b = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name=f'{SCHOOL_TOKENS["b"]} community', school=self.school_b,
            is_public=True, created_by=self.counselor_b,
        )
        ChannelMembership.objects.create(channel=self.community_b, user=self.counselor_b, role=ChannelMembership.Role.OWNER)

    # -- scopes -------------------------------------------------------------

    def owners_visible_to(self, actor):
        if actor.role == User.Role.COUNSELOR:
            return {owner for owner, counselor in self.counselors.items() if counselor.pk == actor.pk}
        school = actor.school_id
        return {owner for owner, counselor in self.counselors.items() if counselor.school_id == school}

    def split(self, actor):
        """(allowed student ids, foreign student ids, foreign tokens) for ``actor``."""
        owners = self.owners_visible_to(actor)
        allowed, foreign = set(), set()
        for (owner, _), profile in self.students.items():
            (allowed if owner in owners else foreign).add(profile.pk)
        tokens = {self.tokens[pk] for pk in foreign}
        tokens |= {tok for key, tok in SCHOOL_TOKENS.items() if getattr(self, f'school_{key}').pk != actor.school_id}
        return allowed, foreign, tokens

    def foreign_records(self, actor, kind):
        _, foreign, _ = self.split(actor)
        return [self.records[pk][kind] for pk in sorted(foreign)]

    def own_record(self, kind):
        return self.records[self.students[('a1', 0)].pk][kind]

    # -- leak detection ------------------------------------------------------

    def student_ids_in(self, data):
        found = set()
        if isinstance(data, dict):
            for key, value in data.items():
                if key in {'student', 'student_id'} and isinstance(value, int):
                    found.add(value)
                else:
                    found |= self.student_ids_in(value)
        elif isinstance(data, list):
            for item in data:
                found |= self.student_ids_in(item)
        return found

    def body_text(self, response):
        data = getattr(response, 'data', None)
        if data is not None:
            try:
                return json.dumps(data, default=str).lower()
            except TypeError:
                pass
        return response.content.decode('utf-8', 'replace').lower()

    def assert_no_leak(self, actor, response, label):
        _, foreign, foreign_tokens = self.split(actor)
        text = self.body_text(response)
        hits = sorted(tok for tok in foreign_tokens if tok in text)
        ids = self.student_ids_in(getattr(response, 'data', None)) & foreign
        if hits or ids:
            self.fail(
                f'REAL LEAK [{actor.username} role={actor.role}] {label}: '
                f'foreign tokens={hits} foreign student ids={sorted(ids)}'
            )

    def get(self, actor, path, params=None, expect=200):
        self.client.force_authenticate(actor)
        response = self.client.get(path, params or {})
        with self.subTest(actor=actor.username, path=path, params=params):
            self.assertEqual(response.status_code, expect, (path, params, getattr(response, 'data', None)))
            self.assert_no_leak(actor, response, f'GET {path} {params or ""}')
        return response

    def assert_refused(self, actor, method, path, data=None, label=None):
        self.client.force_authenticate(actor)
        response = getattr(self.client, method)(path, data or {}, format='json')
        label = label or f'{method.upper()} {path}'
        with self.subTest(actor=actor.username, call=label):
            if 200 <= response.status_code < 300:
                self.fail(
                    f'REAL LEAK [{actor.username} role={actor.role}] {label} -> {response.status_code} '
                    f'(acted on another scope): {getattr(response, "data", None)}'
                )
            if response.status_code not in REFUSED:
                self.fail(
                    f'UNEXPECTED STATUS [{actor.username}] {label} -> {response.status_code}, wanted 403/404: '
                    f'{getattr(response, "data", None)}'
                )
            self.assert_no_leak(actor, response, label)
        return response


class CounselorReadIsolationTests(TenantIsolationFixture, APITestCase):
    """Counselor a1 reads every counselor surface; nothing of a2, b1 or b2 shows up."""

    def setUp(self):
        super().setUp()
        self.a1 = User.objects.select_related('school').get(pk=self.counselor.pk)
        self.allowed, self.foreign, _ = self.split(self.a1)

    def test_dashboard_stats_and_home(self):
        plain = self.get(self.a1, '/api/dashboard/stats/')
        self.assertEqual(plain.data['students_total'], 2)
        self.assertEqual(plain.data['tasks_total'], 4)
        for key in ('tasks', 'documents', 'roadmap', 'portfolio', 'essays'):
            self.assertEqual(plain.data['review'][key], 2, f'review.{key} counts another scope: {plain.data["review"]}')
        home = self.get(self.a1, '/api/dashboard/stats/', {'include': 'home'})
        self.assertIn('home', home.data)
        # The home lists only name a1's students (and the own tokens show up, so the check is not vacuous).
        self.assertTrue(self.student_ids_in(home.data['home']) <= self.allowed)
        self.assertIn(token('a1', 0), self.body_text(home))

    def test_students_list_detail_and_filters(self):
        listed = self.get(self.a1, '/api/students/')
        self.assertEqual({row['id'] for row in self.results(listed)}, self.allowed)
        for params in (
            {'search': 'zqx'}, {'counselor': self.counselor_peer.pk}, {'counselor': self.counselor_b.pk},
            {'school': self.school_b.pk}, {'unassigned': 'true'}, {'page_size': 100},
        ):
            response = self.get(self.a1, '/api/students/', params)
            self.assertLessEqual({row['id'] for row in self.results(response)}, self.allowed, params)
        own = self.students[('a1', 0)]
        self.get(self.a1, f'/api/students/{own.pk}/')
        for pk in sorted(self.foreign):
            for suffix in ('', 'xp-history/', 'data-visibility/', 'cv/', 'photo/'):
                self.assert_refused(self.a1, 'get', f'/api/students/{pk}/{suffix}')

    def test_record_lists_with_every_review_filter(self):
        foreign_student = self.students[('a2', 0)].pk
        foreign_school_student = self.students[('b1', 0)].pk
        lists = {
            'tasks': [{}, {'status': 'submitted'}, {'status': 'submitted', 'ordering': 'created'}, {'open': 'true'},
                      {'open': 'false'}, {'search': 'zqx'}],
            'documents': [{}, {'awaiting_review': 'true'}, {'awaiting_review': 'false'}, {'status': 'uploaded'}],
            'achievements': [{}, {'awaiting_review': 'true'}, {'awaiting_review': 'false'}, {'verified': 'false'}],
            'roadmap-missions': [{}, {'status': 'submitted'}, {'ordering': 'sequence'}],
            'essays': [{}, {'status': 'reviewing'}, {'status': 'reviewing', 'ordering': 'created'}],
            'applications': [{}],
            'meetings': [{}],
            'activity': [{}],
            'student-messages': [{}],
        }
        for endpoint, variants in lists.items():
            for params in variants:
                response = self.get(self.a1, f'/api/{endpoint}/', params)
                rows = self.results(response)
                self.assertLessEqual({row['student'] for row in rows}, self.allowed, (endpoint, params))
                # Filters naming someone else's student, counselor or school narrow to nothing.
                for extra in (
                    {'student': foreign_student}, {'student': foreign_school_student},
                    {'counselor': self.counselor_peer.pk}, {'school': self.school_b.pk},
                ):
                    if endpoint == 'student-messages':
                        continue
                    narrowed = self.get(self.a1, f'/api/{endpoint}/', {**params, **extra})
                    self.assertEqual(self.results(narrowed), [], (endpoint, params, extra))
        # The review queue is not vacuous: a1 sees exactly their own two submitted tasks.
        queue = self.results(self.get(self.a1, '/api/tasks/', {'status': 'submitted'}))
        self.assertEqual(len(queue), 2)

    def test_record_details_of_other_scopes_are_not_found(self):
        for kind in ('tasks', 'documents', 'achievements', 'roadmap-missions', 'essays', 'meetings', 'activity',
                     'notifications', 'student-messages', 'bookings'):
            for record in self.foreign_records(self.a1, kind):
                self.assert_refused(self.a1, 'get', f'/api/{kind}/{record.pk}/')
                if kind not in {'activity'}:
                    self.assert_refused(self.a1, 'patch', f'/api/{kind}/{record.pk}/', {'title': 'x'})

    def test_notifications_every_view(self):
        for params in ({}, {'mine': 'true'}, {'unread': 'true'}, {'mine': 'true', 'unread': 'true'}):
            response = self.get(self.a1, '/api/notifications/', params)
            for row in self.results(response):
                self.assertIn(row['student'], self.allowed, (params, row))
        summary = self.get(self.a1, '/api/notifications/summary/')
        # Only a1's own addressed notices count on the bell (one per own student).
        self.assertEqual(summary.data['unread'], 2, summary.data)

    def test_message_channels_and_messages(self):
        response = self.get(self.a1, '/api/message-channels/')
        ids = {row['id'] for row in self.results(response)}
        self.assertIn(self.channels['a1'].pk, ids)
        for channel in (self.channels['a2'], self.channels['b1'], self.channels['b2'], self.community_b):
            self.assertNotIn(channel.pk, ids, channel.name)
            self.assert_refused(self.a1, 'get', f'/api/message-channels/{channel.pk}/')
            listed = self.client.get('/api/channel-messages/', {'channel': channel.pk})
            with self.subTest(channel=channel.name):
                if listed.status_code == 200:
                    self.assert_no_leak(self.a1, listed, f'GET /api/channel-messages/?channel={channel.pk}')
                else:
                    self.assertIn(listed.status_code, REFUSED)
        for params in ({'search': 'zqx'}, {'kind': 'group'}, {'kind': 'community'}):
            self.get(self.a1, '/api/message-channels/', params)
        self.get(self.a1, '/api/message-channels/overview/')
        # Contacts are school-wide by design; only another school is a leak here.
        contacts = self.get(self.a1, '/api/message-channels/contacts/')
        schools = set(User.objects.filter(pk__in=[row['id'] for row in contacts.data]).values_list('school_id', flat=True))
        self.assertLessEqual(schools, {self.school_a.pk, None}, 'REAL LEAK: contacts reach another school')

    def test_search(self):
        response = self.get(self.a1, '/api/search/', {'q': 'zqx'})
        self.assertIn(token('a1', 0), self.body_text(response))

    def test_bookings_list_and_availability_read(self):
        for params in ({}, {'status': 'pending'}, {'student': self.students[('a2', 0)].pk},
                       {'participant': self.counselor_peer.pk}, {'search': 'zqx'}):
            response = self.get(self.a1, '/api/bookings/', params)
            for row in self.results(response):
                self.assertIn(row['student'], self.allowed)
                self.assertEqual(row['participant'], self.a1.pk)
        slots = self.get(self.a1, '/api/bookings/availability/')
        self.assertEqual({row['id'] for row in slots.data}, {self.slots['a1'].pk})


class CounselorActionIsolationTests(TenantIsolationFixture, APITestCase):
    """Counselor a1 acts on ids of other scopes: always 403/404, nothing changes."""

    def setUp(self):
        super().setUp()
        self.a1 = User.objects.select_related('school').get(pk=self.counselor.pk)

    def test_approve_and_send_back(self):
        for kind in ('tasks', 'documents', 'achievements', 'roadmap-missions'):
            model = type(self.own_record(kind))
            for record in self.foreign_records(self.a1, kind):
                before = model.objects.filter(pk=record.pk).values().first()
                self.assert_refused(self.a1, 'post', f'/api/{kind}/{record.pk}/approve/', {'note': 'ok'})
                self.assert_refused(self.a1, 'post', f'/api/{kind}/{record.pk}/send-back/', {'note': 'fix'})
                self.assertEqual(model.objects.filter(pk=record.pk).values().first(), before, (kind, record.pk))
            # Positive control: the same calls on a1's own record work.
            self.client.force_authenticate(self.a1)
            own = self.own_record(kind)
            response = self.client.post(f'/api/{kind}/{own.pk}/approve/', {'note': 'ok'}, format='json')
            self.assertEqual(response.status_code, 200, (kind, response.data))

    def test_check_in(self):
        today = timezone.localdate().isoformat()
        for pk in sorted(self.split(self.a1)[1]):
            before = ActivityLog.objects.filter(student_id=pk).count()
            self.assert_refused(self.a1, 'post', '/api/dashboard/stats/', {'student': pk, 'date': today, 'checked': True})
            self.assertEqual(ActivityLog.objects.filter(student_id=pk).count(), before)
        self.client.force_authenticate(self.a1)
        own = self.students[('a1', 0)].pk
        ok = self.client.post('/api/dashboard/stats/', {'student': own, 'date': today, 'checked': True}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)

    def test_booking_actions(self):
        later = (self.future(days=9)).isoformat()
        for booking in self.foreign_records(self.a1, 'bookings'):
            before = Booking.objects.filter(pk=booking.pk).values().first()
            for verb in ('approve', 'reject', 'complete', 'cancel'):
                self.assert_refused(self.a1, 'post', f'/api/bookings/{booking.pk}/{verb}/')
            self.assert_refused(self.a1, 'post', f'/api/bookings/{booking.pk}/reschedule/', {'starts_at': later})
            self.assert_refused(self.a1, 'delete', f'/api/bookings/{booking.pk}/')
            self.assertEqual(Booking.objects.filter(pk=booking.pk).values().first(), before)
        # Staff cannot book another counselor's student, nor claim another counselor's slot.
        for pk in sorted(self.split(self.a1)[1]):
            self.client.force_authenticate(self.a1)
            response = self.client.post('/api/bookings/', {
                'student': pk, 'topic': 'x', 'starts_at': self.future(days=11).isoformat(),
            }, format='json')
            with self.subTest(booking_for=pk):
                self.assertFalse(200 <= response.status_code < 300, f'REAL LEAK: a1 booked student {pk}')
        response = self.client.post('/api/bookings/', {
            'student': self.students[('a1', 0)].pk, 'topic': 'x', 'starts_at': self.slots['a2'].starts_at.isoformat(),
            'availability_slot': self.slots['a2'].pk,
        }, format='json')
        self.assertFalse(200 <= response.status_code < 300, 'REAL LEAK: a1 booked onto a2\'s slot')
        own = self.own_record('bookings')
        self.client.force_authenticate(self.a1)
        self.assertEqual(self.client.post(f'/api/bookings/{own.pk}/approve/').status_code, 200)

    def test_availability_patch_delete_repeat(self):
        for owner in ('a2', 'b1', 'b2'):
            slot = self.slots[owner]
            before = MeetingAvailability.objects.filter(pk=slot.pk).values().first()
            self.assert_refused(self.a1, 'patch', '/api/bookings/availability/', {
                'id': slot.pk, 'starts_at': self.future(days=20).isoformat(),
            })
            self.assert_refused(self.a1, 'delete', '/api/bookings/availability/', {'id': slot.pk})
            self.assertEqual(MeetingAvailability.objects.filter(pk=slot.pk).values().first(), before)
        start = timezone.localdate() + timedelta(days=1)
        self.client.force_authenticate(self.a1)
        response = self.client.post('/api/bookings/availability/repeat/', {
            'weekdays': list(range(7)), 'time': '08:00', 'start_date': start.isoformat(),
            'end_date': (start + timedelta(days=7)).isoformat(), 'duration_minutes': 30,
        }, format='json')
        self.assertIn(response.status_code, {200, 201}, response.data)
        created = [row['id'] for row in response.data['slots']]
        self.assertTrue(created)
        self.assertEqual(
            set(MeetingAvailability.objects.filter(pk__in=created).values_list('participant_id', flat=True)),
            {self.a1.pk},
        )
        # Own slot PATCH and DELETE still work (positive control).
        own = self.slots['a1']
        moved = self.client.patch('/api/bookings/availability/', {
            'id': own.pk, 'starts_at': self.future(days=21).isoformat(),
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(self.client.delete('/api/bookings/availability/', {'id': own.pk}, format='json').status_code, 204)

    def test_notification_read_and_read_all(self):
        foreign = self.foreign_records(self.a1, 'notifications') + self.foreign_records(self.a1, 'addressed')
        for notice in foreign:
            self.assert_refused(self.a1, 'post', f'/api/notifications/{notice.pk}/read/')
            self.assert_refused(self.a1, 'delete', f'/api/notifications/{notice.pk}/')
        self.client.force_authenticate(self.a1)
        response = self.client.post('/api/notifications/read-all/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['updated'], 2, 'read-all touched notices outside a1\'s bell')
        still_unread = Notification.objects.filter(pk__in=[notice.pk for notice in foreign], is_read=False).count()
        self.assertEqual(still_unread, len(foreign), 'REAL LEAK: read-all marked another scope\'s notices read')
        own = self.own_record('notifications')
        self.assertEqual(self.client.post(f'/api/notifications/{own.pk}/read/').status_code, 200)

    def test_student_actions(self):
        for pk in sorted(self.split(self.a1)[1]):
            self.assert_refused(self.a1, 'post', f'/api/students/{pk}/section-review/', {
                'section': 'personal', 'status': 'approved',
            })
            self.assert_refused(self.a1, 'post', f'/api/students/{pk}/approve-level/')
            self.assert_refused(self.a1, 'post', f'/api/students/{pk}/remind/')
            self.assert_refused(self.a1, 'patch', f'/api/students/{pk}/', {'notes': 'x'})
            self.assert_refused(self.a1, 'post', '/api/roadmap-missions/extend-level-one/', {'student': pk})
            self.client.force_authenticate(self.a1)
            response = self.client.post('/api/tasks/', {'student': pk, 'title': 'x', 'due_date': '2030-01-01'}, format='json')
            with self.subTest(create_task_for=pk):
                self.assertFalse(200 <= response.status_code < 300, f'REAL LEAK: a1 created a task for student {pk}')
            response = self.client.post('/api/student-messages/', {'student': pk, 'body': 'x'}, format='json')
            with self.subTest(message_for=pk):
                self.assertFalse(200 <= response.status_code < 300, f'REAL LEAK: a1 messaged student {pk}')

    def test_essay_writes(self):
        for essay in self.foreign_records(self.a1, 'essays'):
            before = Essay.objects.filter(pk=essay.pk).values().first()
            self.assert_refused(self.a1, 'patch', f'/api/essays/{essay.pk}/', {
                'status': 'approved', 'counselor_comment': 'x',
            })
            self.assert_refused(self.a1, 'delete', f'/api/essays/{essay.pk}/')
            self.assertEqual(Essay.objects.filter(pk=essay.pk).values().first(), before)

    def test_channel_writes(self):
        for channel in (self.channels['a2'], self.channels['b1'], self.community_b):
            self.client.force_authenticate(self.a1)
            response = self.client.post('/api/channel-messages/', {'channel': channel.pk, 'body': 'x'}, format='json')
            with self.subTest(channel=channel.name):
                self.assertFalse(200 <= response.status_code < 300, f'REAL LEAK: a1 posted into {channel.name}')
            self.assert_refused(self.a1, 'post', f'/api/message-channels/{channel.pk}/mark-read/')


class SchoolStaffIsolationTests(TenantIsolationFixture, APITestCase):
    """Organization and teacher of school A see school A (both counselors) and nothing of school B."""

    READS = (
        ('/api/dashboard/stats/', {}),
        ('/api/students/', {}),
        ('/api/students/', {'school': None}),
        ('/api/tasks/', {}),
        ('/api/tasks/', {'status': 'submitted'}),
        ('/api/roadmap-missions/', {}),
        ('/api/documents/', {}),
        ('/api/achievements/', {}),
        ('/api/essays/', {}),
        ('/api/applications/', {}),
        ('/api/activity/', {}),
        ('/api/meetings/', {}),
        ('/api/notifications/', {}),
        ('/api/notifications/', {'mine': 'true'}),
        ('/api/notifications/summary/', {}),
        ('/api/bookings/', {}),
        ('/api/bookings/availability/', {}),
        ('/api/message-channels/', {}),
        ('/api/search/', {'q': 'zqx'}),
    )

    def staff(self):
        return [User.objects.select_related('school').get(pk=pk) for pk in (self.organization.pk, self.teacher.pk)]

    def test_reads_stay_in_school(self):
        for actor in self.staff():
            self.client.force_authenticate(actor)
            for path, params in self.READS:
                params = {key: (self.school_b.pk if value is None else value) for key, value in params.items()}
                response = self.client.get(path, params)
                with self.subTest(actor=actor.username, path=path, params=params):
                    if response.status_code in REFUSED:
                        continue  # the role cannot use this list at all
                    self.assertEqual(response.status_code, 200, (path, getattr(response, 'data', None)))
                    self.assert_no_leak(actor, response, f'GET {path} {params}')
            stats = self.client.get('/api/dashboard/stats/')
            self.assertEqual(stats.data['students_total'], 4, actor.username)

    def test_foreign_school_ids_refused(self):
        for actor in self.staff():
            for kind in ('tasks', 'documents', 'achievements', 'roadmap-missions', 'essays', 'meetings',
                         'notifications', 'activity', 'bookings'):
                for record in self.foreign_records(actor, kind):
                    self.assert_refused(actor, 'get', f'/api/{kind}/{record.pk}/')
            for kind in ('tasks', 'roadmap-missions'):
                for record in self.foreign_records(actor, kind):
                    self.assert_refused(actor, 'post', f'/api/{kind}/{record.pk}/approve/', {'note': 'x'})
                    self.assert_refused(actor, 'post', f'/api/{kind}/{record.pk}/send-back/', {'note': 'x'})
            for pk in sorted(self.split(actor)[1]):
                self.assert_refused(actor, 'get', f'/api/students/{pk}/')
            for owner in ('b1', 'b2'):
                self.assert_refused(actor, 'patch', '/api/bookings/availability/', {
                    'id': self.slots[owner].pk, 'starts_at': self.future(days=30).isoformat(),
                })
                self.assert_refused(actor, 'delete', '/api/bookings/availability/', {'id': self.slots[owner].pk})
            self.assert_refused(actor, 'get', f'/api/message-channels/{self.channels["b1"].pk}/')
            self.assert_refused(actor, 'get', f'/api/message-channels/{self.community_b.pk}/')
            self.client.force_authenticate(actor)
            check_in = self.client.post('/api/dashboard/stats/', {
                'student': self.students[('a1', 0)].pk, 'date': timezone.localdate().isoformat(), 'checked': True,
            }, format='json')
            self.assertEqual(check_in.status_code, 403, (actor.username, check_in.data))

    def test_school_b_counselor_mirror(self):
        """The mirror image: b2 sees none of school A and none of b1."""
        b2 = User.objects.select_related('school').get(pk=self.counselor_b2.pk)
        for path, params in (
            ('/api/dashboard/stats/', {'include': 'home'}), ('/api/students/', {}), ('/api/tasks/', {'status': 'submitted'}),
            ('/api/documents/', {'awaiting_review': 'true'}), ('/api/achievements/', {'awaiting_review': 'true'}),
            ('/api/roadmap-missions/', {'status': 'submitted'}), ('/api/essays/', {'status': 'reviewing'}),
            ('/api/bookings/', {}), ('/api/notifications/', {}), ('/api/notifications/summary/', {}),
            ('/api/message-channels/', {}), ('/api/activity/', {}), ('/api/meetings/', {}), ('/api/search/', {'q': 'zqx'}),
        ):
            self.get(b2, path, params)
        self.assertEqual(self.get(b2, '/api/dashboard/stats/').data['students_total'], 2)


class SchoolIsolationSanityTests(TenantIsolationFixture, APITestCase):
    def test_fixture_shape(self):
        self.assertEqual(School.objects.filter(pk__in=[self.school_a.pk, self.school_b.pk]).count(), 2)
        self.assertEqual(len(self.students), 8)
        a1, foreign, tokens = self.split(self.counselor)
        self.assertEqual(len(a1), 2)
        self.assertEqual(len(foreign), 6)
