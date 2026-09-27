"""Role isolation: bookings, program services, store, team and screen time."""
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import (
    Booking,
    Notification,
    ProgramService,
    ScreenTimeDaily,
    StoreItem,
)
from .base import RoleIsolationBase


class PortalRoleIsolationTests(RoleIsolationBase):
    def test_student_booking_participant_approval_and_notification(self):
        self.client.force_authenticate(self.student_a_user)
        participants = self.client.get('/api/bookings/participants/')
        self.assertEqual(participants.status_code, status.HTTP_200_OK)
        participant_ids = {item['id'] for item in participants.data}
        self.assertTrue({self.counselor.id, self.teacher.id, self.organization.id}.issubset(participant_ids))
        self.assertNotIn(self.student_b_user.id, participant_ids)

        booking = self.client.post(
            '/api/bookings/',
            {
                'participant': self.counselor.id,
                'topic': 'Essay review',
                'starts_at': '2027-11-20T09:00:00Z',
                'duration_minutes': 45,
            },
            format='json',
        )
        self.assertEqual(booking.status_code, status.HTTP_201_CREATED)
        self.assertEqual(booking.data['student'], self.student_a.id)
        self.assertEqual(booking.data['participant'], self.counselor.id)
        self.assertEqual(booking.data['participant_role'], User.Role.COUNSELOR)
        self.assertEqual(booking.data['status'], Booking.Status.PENDING)

        message = self.client.post('/api/student-messages/', {'body': 'Could you review my outline?'}, format='json')
        self.assertEqual(message.status_code, status.HTTP_201_CREATED)
        self.assertEqual(message.data['sender'], self.student_a_user.id)
        self.assertEqual(message.data['recipient'], self.counselor.id)

        self.client.force_authenticate(self.counselor)
        counselor_messages = self.results(self.client.get('/api/student-messages/'))
        self.assertEqual([item['id'] for item in counselor_messages], [message.data['id']])
        reply = self.client.post(
            '/api/student-messages/',
            {'student': self.student_a.id, 'body': 'Your outline is ready for review.'},
            format='json',
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reply.data['sender'], self.counselor.id)
        self.assertEqual(reply.data['recipient'], self.student_a_user.id)

        counselor_bookings = self.results(self.client.get('/api/bookings/'))
        self.assertEqual([item['id'] for item in counselor_bookings], [booking.data['id']])
        approved = self.client.post(
            f"/api/bookings/{booking.data['id']}/approve/",
            {},
            format='json',
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data['status'], Booking.Status.APPROVED)
        notification = Notification.objects.get(student=self.student_a, title='Meeting approved')
        self.assertIn('Essay review', booking.data['topic'])
        self.assertIn('approved', notification.message)

        completed = self.client.post(f"/api/bookings/{booking.data['id']}/complete/", {}, format='json')
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(completed.data['status'], Booking.Status.COMPLETED)
        self.assertTrue(Notification.objects.filter(student=self.student_a, title='Meeting completed').exists())

    def test_booking_is_limited_to_related_staff_and_target_participant(self):
        other_school_staff = User.objects.create_user(
            username='organization-b-booking',
            email='organization-b-booking@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_b,
        )
        self.client.force_authenticate(self.student_a_user)
        blocked = self.client.post(
            '/api/bookings/',
            {
                'participant': other_school_staff.id,
                'topic': 'Wrong school meeting',
                'starts_at': '2027-11-20T09:00:00Z',
                'duration_minutes': 45,
            },
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)

        teacher_booking = self.client.post(
            '/api/bookings/',
            {
                'participant': self.teacher.id,
                'topic': 'Academic planning',
                'starts_at': '2027-11-21T09:00:00Z',
                'duration_minutes': 30,
            },
            format='json',
        )
        self.assertEqual(teacher_booking.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.organization)
        self.assertEqual(self.results(self.client.get('/api/bookings/')), [])
        forbidden = self.client.post(f"/api/bookings/{teacher_booking.data['id']}/approve/", {}, format='json')
        self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.teacher)
        visible = self.results(self.client.get('/api/bookings/'))
        self.assertEqual([item['id'] for item in visible], [teacher_booking.data['id']])
        rejected = self.client.post(f"/api/bookings/{teacher_booking.data['id']}/reject/", {}, format='json')
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.data['status'], Booking.Status.REJECTED)

    def test_student_reads_program_store_and_team(self):
        ProgramService.objects.create(student=self.student_a, name='Admissions strategy', unlimited=True)
        ProgramService.objects.create(student=self.student_b, name='Private service', unlimited=True)
        StoreItem.objects.filter(catalog_key__isnull=False).delete()  # migrated catalog snapshot
        StoreItem.objects.create(title='University Match', category='Planning')
        self.client.force_authenticate(self.student_a_user)

        services = self.results(self.client.get('/api/program-services/'))
        self.assertEqual([item['name'] for item in services], ['Admissions strategy'])
        self.assertEqual(len(self.results(self.client.get('/api/store-items/'))), 1)
        team = self.client.get('/api/student-team/')
        self.assertEqual(team.status_code, status.HTTP_200_OK)
        self.assertEqual(team.data[0]['id'], self.counselor.id)

    def test_counselor_manages_program_services_only_for_assigned_school_students(self):
        self.client.force_authenticate(self.counselor)
        created = self.client.post(
            '/api/program-services/',
            {
                'student': self.student_a.id,
                'name': 'Essay mentorship',
                'category': 'Application support',
                'mentor': self.counselor.id,
                'total_hours': '12.0',
                'used_hours': '2.5',
                'status': ProgramService.Status.ACTIVE,
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['student_name'], self.student_a_user.get_full_name() or self.student_a_user.username)
        self.assertEqual(created.data['remaining_hours'], 9.5)
        self.assertEqual(created.data['mentor_role'], User.Role.COUNSELOR)

        updated = self.client.patch(
            f"/api/program-services/{created.data['id']}/",
            {'used_hours': '5.0'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        self.assertEqual(updated.data['remaining_hours'], 7.0)

        blocked = self.client.post(
            '/api/program-services/',
            {
                'student': self.student_b.id,
                'name': 'Cross-school service',
                'unlimited': True,
            },
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProgramService.objects.filter(name='Cross-school service').exists())

    def test_organization_reads_own_program_services_but_cannot_write(self):
        own = ProgramService.objects.create(student=self.student_a, name='Own school service', unlimited=True)
        ProgramService.objects.create(student=self.student_b, name='Other school service', unlimited=True)
        self.client.force_authenticate(self.organization)
        listed = self.results(self.client.get('/api/program-services/'))
        self.assertEqual([item['id'] for item in listed], [own.id])
        denied = self.client.post(
            '/api/program-services/',
            {'student': self.student_a.id, 'name': 'Not allowed', 'unlimited': True},
            format='json',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_screen_time_tracks_aggregate_active_seconds_and_student_sees_only_self(self):
        self.client.force_authenticate(self.student_a_user)
        payload = {'entries': [
            {'date': timezone.localdate().isoformat(), 'page': 'roadmap', 'seconds': 24},
            {'date': timezone.localdate().isoformat(), 'page': 'roadmap', 'seconds': 16},
        ]}
        first = self.client.post('/api/screen-time/track/', payload, format='json')
        second = self.client.post('/api/screen-time/track/', {'entries': [payload['entries'][0]]}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        record = ScreenTimeDaily.objects.get(user=self.student_a_user, page='roadmap')
        self.assertEqual(record.active_seconds, 64)
        self.assertEqual(record.sessions, 2)
        summary = self.client.get('/api/screen-time/summary/?days=7')
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data['own']['today_seconds'], 64)
        self.assertEqual(summary.data['team'], [])
        listed = self.results(self.client.get('/api/screen-time/'))
        self.assertEqual({row['user'] for row in listed}, {self.student_a_user.id})

    def test_screen_time_staff_summary_is_limited_to_permitted_students(self):
        today = timezone.localdate()
        ScreenTimeDaily.objects.create(user=self.student_a_user, date=today, page='roadmap', active_seconds=120)
        ScreenTimeDaily.objects.create(user=self.student_b_user, date=today, page='messages', active_seconds=900)
        self.client.force_authenticate(self.counselor)
        summary = self.client.get('/api/screen-time/summary/?days=7')
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual([item['student'] for item in summary.data['team']], [self.student_a.id])
        self.assertEqual(summary.data['team'][0]['today_seconds'], 120)
        listed = self.results(self.client.get('/api/screen-time/'))
        self.assertNotIn(self.student_b_user.id, {row['user'] for row in listed})
