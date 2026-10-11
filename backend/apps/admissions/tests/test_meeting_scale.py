from datetime import datetime, time, timedelta
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.users.models import User

from ..models import Booking, MeetingAvailability
from .base import RoleIsolationBase


class MeetingScaleTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.start = (timezone.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)

    def _repeat_queries(self, weeks):
        first = timezone.localdate() + timedelta(days=1)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post('/api/bookings/availability/repeat/', {
                'weekdays': list(range(7)), 'time': '10:00', 'duration_minutes': 30,
                'start_date': first.isoformat(), 'end_date': (first + timedelta(weeks=weeks, days=-1)).isoformat(),
            }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['created'], weeks * 7)
        return len(ctx.captured_queries)

    def test_repeat_weekly_query_count_does_not_grow_with_weeks(self):
        self.client.force_authenticate(self.counselor)
        one_week = self._repeat_queries(1)
        MeetingAvailability.objects.filter(participant=self.counselor).delete()
        twelve_weeks = self._repeat_queries(12)
        self.assertLessEqual(twelve_weeks - one_week, 2)

    def test_repeat_weekly_still_skips_slots_and_open_meetings_from_memory(self):
        first = timezone.localdate() + timedelta(days=1)
        day2 = timezone.make_aware(datetime.combine(first + timedelta(days=1), time(10)))
        day3 = day2 + timedelta(days=1)
        day4 = day3 + timedelta(days=1)
        MeetingAvailability.objects.create(participant=self.counselor, starts_at=day2 + timedelta(minutes=15), duration_minutes=30)
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Open',
                               starts_at=day3 - timedelta(minutes=45), duration_minutes=60, status=Booking.Status.APPROVED)
        # A cancelled meeting does not hold the time.
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Gone',
                               starts_at=day4, duration_minutes=60, status=Booking.Status.CANCELLED)
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/availability/repeat/', {
            'weekdays': list(range(7)), 'time': '10:00', 'duration_minutes': 30,
            'start_date': first.isoformat(), 'end_date': (first + timedelta(days=3)).isoformat(),
        }, format='json')
        self.assertEqual((response.data['created'], response.data['skipped']), (2, 2))
        created = {timezone.localtime(slot.starts_at) for slot in MeetingAvailability.objects.filter(
            participant=self.counselor, duration_minutes=30).exclude(starts_at=day2 + timedelta(minutes=15))}
        self.assertNotIn(day2, created)
        self.assertNotIn(day3, created)
        self.assertIn(day4, created)
        self.assertEqual(len(response.data['slots']), 2)
        self.assertTrue(all(slot['id'] for slot in response.data['slots']))

    def test_staff_cannot_edit_a_slot_with_any_booking_history(self):
        self.client.force_authenticate(self.counselor)
        for status in (Booking.Status.CANCELLED, Booking.Status.REJECTED, Booking.Status.COMPLETED):
            slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
            Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=slot,
                                   topic='Planning', starts_at=self.start, duration_minutes=45, status=status)
            refused = self.client.patch('/api/bookings/availability/', {
                'id': slot.id, 'starts_at': (self.start + timedelta(hours=2)).isoformat(),
            }, format='json')
            self.assertEqual(refused.status_code, 400, status)
            self.assertIn('meeting on record', refused.data['detail'])
            slot.refresh_from_db()
            self.assertEqual(slot.starts_at, self.start)
            slot.delete()

    def test_staff_cannot_move_a_past_slot_into_the_future(self):
        past = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() - timedelta(days=2))
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=past, topic='Done',
                               starts_at=past.starts_at, duration_minutes=45, status=Booking.Status.COMPLETED)
        bare_past = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() - timedelta(days=3))
        self.client.force_authenticate(self.counselor)
        for slot in (past, bare_past):
            refused = self.client.patch('/api/bookings/availability/', {
                'id': slot.id, 'starts_at': self.start.isoformat(),
            }, format='json')
            self.assertEqual(refused.status_code, 400)
            self.assertIn('detail', refused.data)
            moved = MeetingAvailability.objects.get(pk=slot.pk)
            self.assertEqual(moved.starts_at, slot.starts_at)

    def test_bookings_list_query_count_does_not_grow_with_rows(self):
        def list_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get('/api/bookings/')
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries), response

        def add(count, offset):
            for index in range(count):
                slot = MeetingAvailability.objects.create(participant=self.counselor,
                                                          starts_at=self.start + timedelta(hours=offset + index))
                Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=slot,
                                       topic='Planning', starts_at=slot.starts_at, duration_minutes=45)

        for user in (self.counselor, self.student_a_user):
            Booking.objects.all().delete()
            MeetingAvailability.objects.all().delete()
            add(2, 0)
            self.client.force_authenticate(user)
            few, _ = list_queries()
            add(20, 100)
            many, response = list_queries()
            self.assertEqual(few, many, user.username)
            self.assertIn('results', response.data)
            self.assertEqual(response.data['count'], 22)

    def test_student_overview_caps_per_staff_and_never_drops_a_person(self):
        teacher = [MeetingAvailability.objects.create(participant=self.teacher, starts_at=self.start + timedelta(hours=hour))
                   for hour in range(5)]
        # The earliest teacher time is taken: it must not use up a place in the overview.
        Booking.objects.create(student=self.student_b, participant=self.teacher, availability_slot=teacher[0],
                               topic='Taken', starts_at=teacher[0].starts_at, duration_minutes=45)
        own = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(days=1))
        self.client.force_authenticate(self.student_a_user)
        with mock.patch('apps.admissions.meetings.OVERVIEW_SLOTS_PER_PARTICIPANT', 2), \
                mock.patch('apps.admissions.meetings.MAX_OVERVIEW_SLOTS', 3):
            overview = self.client.get('/api/bookings/availability/').data
            self.assertEqual([item['id'] for item in overview], [teacher[1].id, teacher[2].id, own.id])
            # Even a total smaller than the staff count keeps everyone's first time before anyone's second.
            with mock.patch('apps.admissions.meetings.MAX_OVERVIEW_SLOTS', 2):
                firsts = self.client.get('/api/bookings/availability/').data
                self.assertEqual([item['id'] for item in firsts], [teacher[1].id, own.id])
            # One person's list is not cut to the overview size.
            theirs = self.client.get(f'/api/bookings/availability/?participant={self.teacher.id}').data
            self.assertEqual([item['id'] for item in theirs], [slot.id for slot in teacher[1:]])

    def test_staff_availability_marks_slots_with_history_not_editable(self):
        fresh = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start)
        old = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(hours=2))
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=old, topic='Gone',
                               starts_at=old.starts_at, duration_minutes=45, status=Booking.Status.CANCELLED)
        self.client.force_authenticate(self.counselor)
        own = {item['id']: (item['available'], item['editable']) for item in self.client.get('/api/bookings/availability/').data}
        self.assertEqual(own, {fresh.id: (True, True), old.id: (True, False)})

    def test_slot_moved_between_validation_and_lock_is_refused(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        moved_to = self.start + timedelta(days=1)
        real = User.objects.select_for_update

        def staff_moves_it_first(*args, **kwargs):
            MeetingAvailability.objects.filter(pk=slot.pk).update(starts_at=moved_to)
            return real(*args, **kwargs)

        self.client.force_authenticate(self.student_a_user)
        with mock.patch.object(User.objects, 'select_for_update', side_effect=staff_moves_it_first):
            response = self.client.post('/api/bookings/', {
                'participant': self.counselor.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(),
                'duration_minutes': 45, 'availability_slot': slot.id,
            }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data['availability_slot']), 'This time just changed. Pick it again.')
        self.assertFalse(Booking.objects.exists())

    def test_product_admin_cannot_create_a_booking(self):
        admin = User.objects.create_user(username='admin-x', email='admin-x@example.com', password='StrongPass123!',
                                         role=User.Role.ADMIN)
        root = User.objects.create_superuser(username='root-x', email='root-x@example.com', password='StrongPass123!')
        for user in (admin, root):
            self.client.force_authenticate(user)
            response = self.client.post('/api/bookings/', {
                'student': self.student_a.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(), 'duration_minutes': 45,
            }, format='json')
            self.assertEqual(response.status_code, 403, (user.username, response.data))
        self.assertFalse(Booking.objects.exists())

    def test_reschedule_sees_slots_overlapping_only_the_meeting_being_moved(self):
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Planning',
                                         starts_at=self.start, duration_minutes=60, status=Booking.Status.APPROVED)
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start + timedelta(minutes=30),
                                                  duration_minutes=45)
        url = f'/api/bookings/availability/?participant={self.counselor.id}'
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get(url).data, [])
        moving = self.client.get(f'{url}&reschedule={booking.pk}').data
        self.assertEqual([item['id'] for item in moving], [slot.id])
        moved = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': slot.starts_at.isoformat(), 'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        # Staff picker: the same slot reads as free only while moving that meeting.
        other = Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Other',
                                       starts_at=self.start + timedelta(days=2), duration_minutes=60)
        later = MeetingAvailability.objects.create(participant=self.counselor, starts_at=other.starts_at + timedelta(minutes=30))
        self.client.force_authenticate(self.counselor)
        state = lambda query='': {item['id']: item['available'] for item in self.client.get(f'/api/bookings/availability/{query}').data}
        self.assertFalse(state()[later.id])
        self.assertTrue(state(f'?reschedule={other.pk}')[later.id])

    def test_reschedule_id_of_someone_elses_meeting_is_a_404(self):
        theirs = Booking.objects.create(student=self.student_b, participant=self.counselor_b, topic='B',
                                        starts_at=self.start, duration_minutes=60)
        teachers = Booking.objects.create(student=self.student_a, participant=self.teacher, topic='T',
                                          starts_at=self.start, duration_minutes=60)
        MeetingAvailability.objects.create(participant=self.counselor_b, starts_at=self.start + timedelta(minutes=30))
        cases = [
            (self.student_a_user, f'?participant={self.counselor.id}&reschedule={theirs.pk}'),
            (self.student_b_user, f'?participant={self.counselor_b.id}&reschedule={teachers.pk}'),
            (self.counselor, f'?reschedule={teachers.pk}'),
            (self.counselor, f'?reschedule={theirs.pk}'),
            (self.counselor_b, f'?reschedule={teachers.pk}'),
            (self.student_a_user, '?reschedule=999999'),
        ]
        for user, query in cases:
            self.client.force_authenticate(user)
            response = self.client.get(f'/api/bookings/availability/{query}')
            self.assertEqual((response.status_code, response.data), (404, {'detail': 'Meeting not found.'}), (user.username, query))


class MeetingCrossSchoolTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.start = (timezone.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
        self.slot_b = MeetingAvailability.objects.create(participant=self.counselor_b, starts_at=self.start, duration_minutes=45)
        self.slot_a = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)

    def test_student_a_cannot_see_school_b_slots(self):
        self.client.force_authenticate(self.student_a_user)
        overview = self.client.get('/api/bookings/availability/')
        self.assertEqual([item['id'] for item in overview.data], [self.slot_a.id])
        direct = self.client.get(f'/api/bookings/availability/?participant={self.counselor_b.id}')
        self.assertEqual(direct.status_code, 400)
        participants = self.client.get('/api/bookings/participants/').data
        self.assertNotIn(self.counselor_b.id, {person['id'] for person in participants})

    def test_student_a_cannot_book_school_b_slot(self):
        self.client.force_authenticate(self.student_a_user)
        base = {'topic': 'Planning', 'starts_at': self.start.isoformat(), 'duration_minutes': 45}
        for participant in (self.counselor_b.id, self.counselor.id):
            attempt = self.client.post('/api/bookings/', {**base, 'participant': participant,
                                                          'availability_slot': self.slot_b.id}, format='json')
            self.assertEqual(attempt.status_code, 400, attempt.data)
        # The other school's slot id fails exactly like a missing id.
        missing = self.client.post('/api/bookings/', {**base, 'participant': self.counselor.id,
                                                      'availability_slot': 999999}, format='json')
        crossed = self.client.post('/api/bookings/', {**base, 'participant': self.counselor.id,
                                                      'availability_slot': self.slot_b.id}, format='json')
        self.assertEqual(missing.data['availability_slot'], crossed.data['availability_slot'])
        self.assertFalse(Booking.objects.filter(availability_slot=self.slot_b).exists())

    def test_student_a_cannot_reschedule_onto_school_b_slot(self):
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=self.slot_a,
                                         topic='Planning', starts_at=self.start, duration_minutes=45)
        later_b = MeetingAvailability.objects.create(participant=self.counselor_b, starts_at=self.start + timedelta(days=1),
                                                     duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        moved = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': later_b.starts_at.isoformat(), 'duration_minutes': 45, 'availability_slot': later_b.id,
        }, format='json')
        self.assertEqual(moved.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.availability_slot_id, self.slot_a.id)

    def test_staff_a_cannot_book_or_touch_a_school_b_student(self):
        for staff in (self.counselor, self.teacher, self.organization):
            self.client.force_authenticate(staff)
            attempt = self.client.post('/api/bookings/', {
                'student': self.student_b.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(), 'duration_minutes': 30,
            }, format='json')
            self.assertEqual(attempt.status_code, 400, staff.username)
            self.assertIn('student', attempt.data)
        self.assertFalse(Booking.objects.filter(student=self.student_b).exists())
        # Nor act on a school B meeting, even one naming them as participant.
        theirs = Booking.objects.create(student=self.student_b, participant=self.counselor, topic='Old',
                                        starts_at=self.start + timedelta(days=1), duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/bookings/{theirs.pk}/reschedule/', {
            'starts_at': (self.start + timedelta(days=2)).isoformat(), 'duration_minutes': 45,
        }, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'/api/bookings/{theirs.pk}/approve/').status_code, 404)
        self.assertNotIn(theirs.id, {item['id'] for item in self.results(self.client.get('/api/bookings/'))})

    def test_staff_cannot_attach_a_slot_or_another_participant(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/', {
            'student': self.student_a.id, 'participant': self.counselor_b.id, 'topic': 'Planning',
            'starts_at': (self.start + timedelta(days=1)).isoformat(), 'duration_minutes': 30,
        }, format='json')
        if response.status_code == 201:
            self.assertEqual(response.data['participant'], self.counselor.id)
        with_slot = self.client.post('/api/bookings/', {
            'student': self.student_a.id, 'topic': 'Planning', 'starts_at': self.start.isoformat(),
            'duration_minutes': 45, 'availability_slot': self.slot_b.id,
        }, format='json')
        self.assertEqual(with_slot.status_code, 400)
        self.assertFalse(Booking.objects.filter(participant=self.counselor_b).exists())
