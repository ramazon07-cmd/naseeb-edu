"""Scale audit: query counts for the student endpoints and the counselor lists at 2 vs 30 students.

The measured table is printed (run with ``-v 2`` or read the captured stdout); the test fails when an endpoint
issues more than ``SLACK`` extra queries for 30 students than for 2, or when a list ignores pagination bounds.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User

from ..models import (
    Achievement, ActivityLog, Application, Booking, ChannelMembership, ChannelMessage, Document, Essay, MeetingAvailability,
    MeetingNote, MessageChannel, Notification, ProgramService, RecommendationLetter, RoadmapMission, School,
    StudentMessage, StudentProfile, Task, University,
)

SLACK = 2
FEW, MANY = 2, 30

COUNSELOR_URLS = (
    '/api/students/', '/api/students/summary/', '/api/tasks/', '/api/applications/', '/api/documents/', '/api/essays/',
    '/api/bookings/', '/api/notifications/', '/api/notifications/summary/', '/api/student-messages/',
    '/api/message-channels/', '/api/message-channels/contacts/', '/api/message-channels/overview/',
    '/api/dashboard/stats/', '/api/dashboard/stats/?include=home', '/api/meetings/', '/api/activity/',
    '/api/roadmap-missions/', '/api/program-services/', '/api/recommendations/', '/api/achievements/',
    '/api/review/today/', '/api/search/?q=aud', '/api/bookings/availability/',
)
STUDENT_URLS = (
    '/api/students/', '/api/tasks/', '/api/applications/', '/api/documents/', '/api/essays/', '/api/essay-lab/essays/',
    '/api/essay-lab/folders/', '/api/bookings/', '/api/bookings/participants/', '/api/bookings/availability/',
    '/api/notifications/', '/api/notifications/summary/', '/api/student-messages/', '/api/message-channels/',
    '/api/message-channels/contacts/', '/api/message-channels/overview/', '/api/student-team/', '/api/roadmap-missions/',
    '/api/program-services/', '/api/dashboard/stats/', '/api/achievements/', '/api/recommendations/',
    '/api/challenge-attempts/', '/api/screen-time/summary/', '/api/college-research/', '/api/my-parents/',
    '/api/telegram/student/', '/api/users/accounts/me/', '/api/opportunity-programs/', '/api/store-items/',
)


class ScaleAuditTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Scale', code='scale')
        self.counselor = self.mk('scale-counselor', User.Role.COUNSELOR)
        self.other_staff = [self.mk(f'scale-teacher-{n}', User.Role.TEACHER) for n in range(3)]
        self.university = University.objects.create(name='Scale University', country='USA')
        self.room = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Room', school=self.school, is_public=True,
        )
        self.serial = 0
        self.students = []

    def mk(self, username, role):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password='StrongPass123!', role=role,
            school=self.school, first_name=username,
        )

    def add_students(self, count):
        today = timezone.localdate()
        for _ in range(count):
            self.serial += 1
            n = self.serial
            user = self.mk(f'aud-student-{n}', User.Role.STUDENT)
            profile = StudentProfile.objects.create(
                user=user, school=self.school, school_name=self.school.name, assigned_counselor=self.counselor,
            )
            self.students.append(profile)
            student = {'student': profile}
            application = Application.objects.create(**student, university=self.university, program='P', status='applying')
            Task.objects.create(**student, title='T', due_date=today, assigned_by=self.counselor)
            Task.objects.create(**student, title='T2', due_date=today - timedelta(days=2), assigned_by=self.counselor)
            Document.objects.create(**student, title='D')
            Essay.objects.create(**student, title='E', application=application, shared_with_counselor=True)
            Achievement.objects.create(**student, title='A', category='olympiad', description='x')
            RecommendationLetter.objects.create(**student, recommender_name='R')
            RoadmapMission.objects.create(**student, title='M', assigned_by=self.counselor)
            ProgramService.objects.create(**student, name='S', mentor=self.counselor, unlimited=True)
            MeetingNote.objects.create(**student, title='N', summary='x', counselor=self.counselor)
            ActivityLog.objects.create(actor=self.counselor, **student, action='A')
            Notification.objects.create(**student, title='N', message='x')
            Notification.objects.create(**student, recipient=self.counselor, title='NC', message='x')
            StudentMessage.objects.create(student=profile, sender=self.counselor, recipient=user, body='hi')
            StudentMessage.objects.create(student=profile, sender=user, recipient=self.counselor, body='yo')
            Booking.objects.create(
                student=profile, participant=self.counselor, topic='B', starts_at=timezone.now() + timedelta(days=2, hours=n),
                status=Booking.Status.PENDING,
            )
            MeetingAvailability.objects.create(
                participant=self.counselor, starts_at=timezone.now() + timedelta(days=3, hours=n),
            )
            group = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name=f'G{n}', school=self.school)
            ChannelMembership.objects.create(channel=group, user=self.counselor, role=ChannelMembership.Role.OWNER)
            ChannelMembership.objects.create(channel=group, user=user)
            ChannelMessage.objects.create(channel=group, sender=user, body='m')
            ChannelMembership.objects.create(channel=self.room, user=user)

    def count(self, actor, url):
        cache.clear()
        self.client.force_authenticate(actor)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertIn(response.status_code, (200, 403, 404), (url, response.status_code))
        return len(queries), response.status_code

    def sweep(self, actor, urls):
        self.add_students(FEW)
        few = {url: self.count(actor, url) for url in urls}
        self.add_students(MANY - FEW)
        many = {url: self.count(actor, url) for url in urls}
        rows = [(url, few[url][0], many[url][0], many[url][1]) for url in urls]
        print(f'\n[audit] {actor.role} {actor.username}: queries at {FEW} vs {MANY} students')
        for url, a, b, status in rows:
            print(f'   {url:48} {a:4} -> {b:4}  (status {status}){"  <-- GROWS" if b - a > SLACK else ""}')
        return [row for row in rows if row[2] - row[1] > SLACK]

    def test_counselor_lists_do_not_grow_with_students(self):
        self.assertEqual(self.sweep(self.counselor, COUNSELOR_URLS), [])

    def test_student_endpoints_do_not_grow_with_classmates_or_own_records(self):
        self.add_students(1)
        actor = self.students[0].user
        self.students.clear()
        actor = User.objects.get(pk=actor.pk)
        self.assertEqual(self.sweep(actor, STUDENT_URLS), [])

    def test_lists_are_bounded(self):
        self.add_students(MANY)
        self.client.force_authenticate(self.counselor)
        for url in ('/api/tasks/', '/api/students/', '/api/notifications/', '/api/bookings/', '/api/message-channels/'):
            response = self.client.get(url + '?page_size=100000')
            self.assertEqual(response.status_code, 200, url)
            data = response.data
            rows = data['results'] if isinstance(data, dict) and 'results' in data else data
            self.assertLessEqual(len(rows), 100, (url, len(rows)))
        # unpaginated custom actions
        for url in ('/api/message-channels/contacts/', '/api/bookings/availability/', '/api/bookings/participants/'):
            response = self.client.get(url)
            self.assertLessEqual(len(response.data), 500, url)
