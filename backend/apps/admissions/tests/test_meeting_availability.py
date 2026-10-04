from datetime import timedelta

from django.utils import timezone

from ..models import Booking, MeetingAvailability
from .base import RoleIsolationBase


class MeetingAvailabilityTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.start = (timezone.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)

    def test_staff_can_offer_time_and_student_can_request_it_once(self):
        self.client.force_authenticate(self.counselor)
        added = self.client.post('/api/bookings/availability/', {
            'starts_at': self.start.isoformat(), 'duration_minutes': 45,
        }, format='json')
        self.assertEqual(added.status_code, 201, added.data)
        slot_id = added.data['id']
        self.client.force_authenticate(self.student_a_user)
        available = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}')
        self.assertEqual(available.status_code, 200)
        self.assertEqual(available.data[0]['available'], True)
        payload = {'participant': self.counselor.id, 'topic': 'Essay review', 'starts_at': self.start.isoformat(),
                   'duration_minutes': 45, 'availability_slot': slot_id}
        booked = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(booked.status_code, 201, booked.data)
        self.assertEqual(booked.data['status'], Booking.Status.PENDING)
        self.assertEqual(self.client.post('/api/bookings/', payload, format='json').status_code, 400)
        self.assertEqual(self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}').data[0]['available'], False)

    def test_student_cannot_use_another_staff_slot_or_create_slots(self):
        other = MeetingAvailability.objects.create(participant=self.teacher, starts_at=self.start, duration_minutes=30)
        hidden = MeetingAvailability.objects.create(participant=self.counselor_b, starts_at=self.start, duration_minutes=30)
        self.client.force_authenticate(self.student_a_user)
        overview = self.client.get('/api/bookings/availability/')
        self.assertEqual(overview.status_code, 200)
        self.assertIn(other.id, {slot['id'] for slot in overview.data})
        self.assertNotIn(hidden.id, {slot['id'] for slot in overview.data})
        self.assertEqual(overview.data[0]['participant'], self.teacher.id)
        self.assertEqual(self.client.post('/api/bookings/availability/', {
            'starts_at': self.start.isoformat(), 'duration_minutes': 30,
        }, format='json').status_code, 403)
        wrong_staff = self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(),
            'duration_minutes': 30, 'availability_slot': other.id,
        }, format='json')
        self.assertEqual(wrong_staff.status_code, 400)
        self.assertEqual(self.client.get(f'/api/bookings/availability/?participant={self.counselor_b.id}').status_code, 400)

    def test_staff_cannot_delete_requested_slot(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=slot,
                               topic='Planning', starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.delete('/api/bookings/availability/', {'id': slot.id}, format='json').status_code, 400)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.delete('/api/bookings/availability/', {'id': slot.id}, format='json').status_code, 404)

    def test_reschedule_moves_reservation_to_new_slot(self):
        first = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        later = self.start + timedelta(days=1)
        second = MeetingAvailability.objects.create(participant=self.counselor, starts_at=later, duration_minutes=30)
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=first,
                                         topic='Planning', starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        moved = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': later.isoformat(), 'duration_minutes': 30, 'availability_slot': second.pk,
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        booking.refresh_from_db()
        self.assertEqual(booking.availability_slot_id, second.id)
        times = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}').data
        self.assertEqual({item['id']: item['available'] for item in times}, {first.id: True, second.id: False})

    def test_manual_meeting_blocks_overlapping_availability(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        Booking.objects.create(student=self.student_a, participant=self.counselor,
                               topic='Existing meeting', starts_at=self.start - timedelta(minutes=15), duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        visible = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}')
        self.assertEqual(visible.data[0]['available'], False)
        attempt = self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(attempt.status_code, 400)
