from datetime import timedelta
from unittest import mock

from django.utils import timezone

from ..models import Booking, MeetingAvailability, Notification
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

    def test_overview_limits_slots_per_staff_member(self):
        early = [MeetingAvailability.objects.create(participant=self.teacher, starts_at=self.start + timedelta(hours=hour))
                 for hour in range(3)]
        late = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=30))
        with mock.patch('apps.admissions.meetings.SLOTS_PER_PARTICIPANT', 2):
            self.client.force_authenticate(self.student_a_user)
            ids = [slot['id'] for slot in self.client.get('/api/bookings/availability/').data]
            self.assertEqual(ids, [early[0].id, early[1].id, late.id])
            self.client.force_authenticate(self.counselor)
            own = self.client.get('/api/bookings/availability/').data
            self.assertEqual([slot['id'] for slot in own], [late.id])

    def test_rescheduling_to_the_held_slot_changes_nothing(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=slot,
                                         topic='Planning', starts_at=self.start, duration_minutes=45,
                                         status=Booking.Status.APPROVED)
        self.client.force_authenticate(self.student_a_user)
        same = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': self.start.isoformat(), 'duration_minutes': 45, 'availability_slot': slot.pk,
        }, format='json')
        self.assertEqual(same.status_code, 200, same.data)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.previous_starts_at), (Booking.Status.APPROVED, None))
        self.assertFalse(Notification.objects.filter(title='Meeting reschedule requested').exists())

    def test_free_form_time_is_allowed_only_when_no_slot_is_open(self):
        taken = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        mine = Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=taken,
                                      topic='Planning', starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        free_form = {'participant': self.counselor.id, 'topic': 'Essays', 'duration_minutes': 30,
                     'starts_at': (self.start + timedelta(days=2)).isoformat()}
        self.assertEqual(self.client.post('/api/bookings/', free_form, format='json').status_code, 201)
        moved = self.client.post(f'/api/bookings/{mine.pk}/reschedule/', {
            'starts_at': (self.start + timedelta(days=3)).isoformat(), 'duration_minutes': 30,
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=5))
        refused = self.client.post('/api/bookings/', {**free_form, 'starts_at': (self.start + timedelta(days=4)).isoformat()},
                                   format='json')
        self.assertEqual(refused.status_code, 400)
        self.assertIn('availability_slot', refused.data)

    def test_duplicate_slot_from_a_concurrent_request_is_a_400(self):
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        # The overlap check ran before the other request committed; the unique start still holds.
        with mock.patch('apps.admissions.views.portal.overlapping', return_value=[]):
            clash = self.client.post('/api/bookings/availability/', {
                'starts_at': self.start.isoformat(), 'duration_minutes': 45,
            }, format='json')
        self.assertEqual(clash.status_code, 400)
        self.assertEqual(str(clash.data['starts_at']), 'This time overlaps an existing slot.')
        self.assertEqual(MeetingAvailability.objects.filter(participant=self.counselor).count(), 1)
