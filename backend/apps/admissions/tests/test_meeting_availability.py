from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

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
        # A taken time disappears for students; the counselor still sees it as requested.
        self.assertEqual(self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}').data, [])
        self.client.force_authenticate(self.counselor)
        own = self.client.get('/api/bookings/availability/').data
        self.assertEqual([(item['id'], item['available']) for item in own], [(slot_id, False)])

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
        self.assertEqual({item['id']: item['available'] for item in times}, {first.id: True})

    def test_manual_meeting_blocks_overlapping_availability(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        Booking.objects.create(student=self.student_a, participant=self.counselor,
                               topic='Existing meeting', starts_at=self.start - timedelta(minutes=15), duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        visible = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}')
        self.assertEqual(visible.data, [])
        attempt = self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(attempt.status_code, 400)

    def test_overview_limits_slots_per_staff_member(self):
        early = [MeetingAvailability.objects.create(participant=self.teacher, starts_at=self.start + timedelta(hours=hour))
                 for hour in range(3)]
        late = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=30))
        with mock.patch('apps.admissions.meetings.OVERVIEW_SLOTS_PER_PARTICIPANT', 2):
            self.client.force_authenticate(self.student_a_user)
            ids = [slot['id'] for slot in self.client.get('/api/bookings/availability/').data]
            self.assertEqual(ids, [early[0].id, early[1].id, late.id])
        with mock.patch('apps.admissions.meetings.SLOTS_PER_PARTICIPANT', 2):
            one = self.client.get(f'/api/bookings/availability/?participant={self.teacher.id}').data
            self.assertEqual([slot['id'] for slot in one], [early[0].id, early[1].id])
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

    def test_student_cannot_book_without_a_slot(self):
        self.client.force_authenticate(self.student_a_user)
        free_form = {'participant': self.counselor.id, 'topic': 'Essays', 'duration_minutes': 30,
                     'starts_at': (self.start + timedelta(days=2)).isoformat()}
        # No slots published at all.
        none_published = self.client.post('/api/bookings/', free_form, format='json')
        self.assertEqual(none_published.status_code, 400)
        self.assertIn('Choose one of the available times.', str(none_published.data['availability_slot']))
        # Every published slot already taken.
        taken = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        Booking.objects.create(student=self.student_b, participant=self.counselor, availability_slot=taken,
                               topic='Planning', starts_at=self.start, duration_minutes=45)
        all_taken = self.client.post('/api/bookings/', free_form, format='json')
        self.assertEqual(all_taken.status_code, 400)
        self.assertIn('Choose one of the available times.', str(all_taken.data['availability_slot']))
        # An open slot elsewhere does not make a free-form time acceptable either.
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=5))
        self.assertEqual(self.client.post('/api/bookings/', free_form, format='json').status_code, 400)
        self.assertFalse(Booking.objects.filter(student=self.student_a).exists())

    def test_student_cannot_reschedule_without_a_slot(self):
        mine = Booking.objects.create(student=self.student_a, participant=self.counselor,
                                      topic='Planning', starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        moved = self.client.post(f'/api/bookings/{mine.pk}/reschedule/', {
            'starts_at': (self.start + timedelta(days=3)).isoformat(), 'duration_minutes': 30,
        }, format='json')
        self.assertEqual(moved.status_code, 400)
        self.assertIn('Choose one of the available times.', str(moved.data['availability_slot']))
        mine.refresh_from_db()
        self.assertEqual(mine.starts_at, self.start)

    def test_staff_edits_a_free_slot(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        other = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(hours=3))
        self.client.force_authenticate(self.counselor)
        later = self.start + timedelta(hours=1)
        edited = self.client.patch('/api/bookings/availability/', {
            'id': slot.id, 'starts_at': later.isoformat(), 'duration_minutes': 60,
        }, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        slot.refresh_from_db()
        self.assertEqual((slot.starts_at, slot.duration_minutes), (later, 60))
        # Overlapping another of my slots is refused, as when adding one.
        clash = self.client.patch('/api/bookings/availability/', {
            'id': slot.id, 'starts_at': (other.starts_at - timedelta(minutes=30)).isoformat(),
        }, format='json')
        self.assertEqual(clash.status_code, 400)
        self.assertIn('starts_at', clash.data)
        # Someone else's slot is not found; students cannot edit.
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.patch('/api/bookings/availability/', {'id': slot.id, 'duration_minutes': 30},
                                           format='json').status_code, 404)
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.patch('/api/bookings/availability/', {'id': slot.id, 'duration_minutes': 30},
                                           format='json').status_code, 403)

    def test_staff_cannot_edit_a_requested_slot(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=slot,
                               topic='Planning', starts_at=self.start, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        refused = self.client.patch('/api/bookings/availability/', {
            'id': slot.id, 'starts_at': (self.start + timedelta(hours=2)).isoformat(),
        }, format='json')
        self.assertEqual(refused.status_code, 400)
        slot.refresh_from_db()
        self.assertEqual(slot.starts_at, self.start)

    def test_repeat_weekly_creates_slots_and_skips_overlaps(self):
        tz = ZoneInfo('Asia/Tokyo')
        first_day = timezone.localdate() + timedelta(days=7)
        tuesday = first_day + timedelta(days=(1 - first_day.weekday()) % 7)
        thursday = tuesday + timedelta(days=2)
        end = tuesday + timedelta(weeks=3, days=2)
        # An existing slot on the second Tuesday at the same time is kept, the new one skipped.
        existing = datetime.combine(tuesday + timedelta(weeks=1), time(15), tzinfo=tz)
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=existing, duration_minutes=30)
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/availability/repeat/', {
            'weekdays': [1, 3], 'time': '15:00', 'duration_minutes': 45,
            'start_date': tuesday.isoformat(), 'end_date': end.isoformat(), 'timezone': 'Asia/Tokyo',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['created'], response.data['skipped']), (7, 1))
        starts = sorted(MeetingAvailability.objects.filter(participant=self.counselor, duration_minutes=45)
                        .values_list('starts_at', flat=True))
        self.assertEqual(len(starts), 7)
        self.assertTrue(all(start.astimezone(tz).hour == 15 and start.astimezone(tz).weekday() in {1, 3} for start in starts))
        self.assertEqual(starts[0].astimezone(tz).date(), tuesday)
        self.assertIn(thursday, {start.astimezone(tz).date() for start in starts})
        # Sending it again creates nothing: every time overlaps.
        again = self.client.post('/api/bookings/availability/repeat/', {
            'weekdays': [1, 3], 'time': '15:00', 'duration_minutes': 45,
            'start_date': tuesday.isoformat(), 'end_date': end.isoformat(), 'timezone': 'Asia/Tokyo',
        }, format='json')
        self.assertEqual((again.status_code, again.data['created'], again.data['skipped']), (200, 0, 8))

    def test_repeat_weekly_is_capped_and_staff_only(self):
        start = timezone.localdate() + timedelta(days=1)
        payload = {'weekdays': [0], 'time': '10:00', 'start_date': start.isoformat(),
                   'end_date': (start + timedelta(weeks=12)).isoformat()}
        self.client.force_authenticate(self.counselor)
        too_long = self.client.post('/api/bookings/availability/repeat/', payload, format='json')
        self.assertEqual(too_long.status_code, 400)
        self.assertIn('end_date', too_long.data)
        bad_zone = self.client.post('/api/bookings/availability/repeat/', {
            **payload, 'end_date': start.isoformat(), 'timezone': 'Mars/Olympus'}, format='json')
        self.assertEqual(bad_zone.status_code, 400)
        self.assertEqual(self.client.post('/api/bookings/availability/repeat/', {
            **payload, 'end_date': (start + timedelta(weeks=12, days=-1)).isoformat()}, format='json').status_code, 201)
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.post('/api/bookings/availability/repeat/', payload, format='json').status_code, 403)

    def test_repeat_weekly_answers_a_racing_slot_like_a_single_one(self):
        start_day = timezone.localdate() + timedelta(days=7)
        taken = datetime.combine(start_day, time(10), tzinfo=timezone.get_current_timezone())
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=taken, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        # Another request added this time after the overlap read: only the unique start catches it.
        with mock.patch('apps.admissions.views.portal.overlapping', return_value=[]):
            response = self.client.post('/api/bookings/availability/repeat/', {
                'weekdays': [start_day.weekday()], 'time': '10:00', 'duration_minutes': 45,
                'start_date': start_day.isoformat(), 'end_date': start_day.isoformat(),
                'timezone': str(timezone.get_current_timezone()),
            }, format='json')
        self.assertEqual((response.status_code, response.data['starts_at']), (400, 'This time overlaps an existing slot.'))
        self.assertEqual(MeetingAvailability.objects.filter(participant=self.counselor).count(), 1)

    def test_repeat_weekly_skips_past_times(self):
        today = timezone.localdate()
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/availability/repeat/', {
            'weekdays': list(range(7)), 'time': '00:00',
            'start_date': (today - timedelta(days=2)).isoformat(), 'end_date': (today + timedelta(days=1)).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['created'], response.data['skipped']), (1, 3))

    def test_staff_booking_cannot_overlap_their_open_meetings(self):
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Existing',
                               starts_at=self.start, duration_minutes=45, status=Booking.Status.APPROVED)
        self.client.force_authenticate(self.counselor)
        payload = {'student': self.student_a.id, 'topic': 'Follow-up', 'duration_minutes': 30,
                   'starts_at': (self.start + timedelta(minutes=30)).isoformat()}
        clash = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(clash.status_code, 400)
        self.assertIn('starts_at', clash.data)
        fine = self.client.post('/api/bookings/', {**payload, 'starts_at': (self.start + timedelta(minutes=45)).isoformat()},
                                format='json')
        self.assertEqual(fine.status_code, 201, fine.data)

    def test_staff_reschedule_checks_overlap_and_may_use_own_slot(self):
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Planning',
                                         starts_at=self.start, duration_minutes=45)
        busy = self.start + timedelta(days=1)
        Booking.objects.create(student=self.student_b, participant=self.counselor, topic='Other',
                               starts_at=busy, duration_minutes=60, status=Booking.Status.APPROVED)
        self.client.force_authenticate(self.counselor)
        url = f'/api/bookings/{booking.pk}/reschedule/'
        clash = self.client.post(url, {'starts_at': (busy + timedelta(minutes=15)).isoformat(), 'duration_minutes': 30},
                                 format='json')
        self.assertEqual(clash.status_code, 400)
        self.assertIn('starts_at', clash.data)
        # Free time stays allowed for staff.
        free = self.start + timedelta(days=2)
        moved = self.client.post(url, {'starts_at': free.isoformat(), 'duration_minutes': 30}, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        # Or one of their own published slots, which the meeting then holds.
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=3))
        to_slot = self.client.post(url, {'starts_at': slot.starts_at.isoformat(), 'duration_minutes': 45,
                                         'availability_slot': slot.id}, format='json')
        self.assertEqual(to_slot.status_code, 200, to_slot.data)
        booking.refresh_from_db()
        self.assertEqual(booking.availability_slot_id, slot.id)
        self.assertEqual(booking.status, Booking.Status.APPROVED)
        # Not a colleague's slot.
        theirs = MeetingAvailability.objects.create(participant=self.teacher, starts_at=self.start + timedelta(days=4))
        self.assertEqual(self.client.post(url, {'starts_at': theirs.starts_at.isoformat(), 'duration_minutes': 45,
                                                'availability_slot': theirs.id}, format='json').status_code, 400)

    def test_students_see_only_free_slots(self):
        free = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start)
        held = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(hours=2))
        Booking.objects.create(student=self.student_b, participant=self.counselor, availability_slot=held,
                               topic='Planning', starts_at=held.starts_at, duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        for url in ('/api/bookings/availability/', f'/api/bookings/availability/?participant={self.counselor.id}'):
            self.assertEqual([item['id'] for item in self.client.get(url).data], [free.id])
        self.client.force_authenticate(self.counselor)
        own = self.client.get('/api/bookings/availability/').data
        self.assertEqual({item['id']: item['available'] for item in own}, {free.id: True, held.id: False})

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
