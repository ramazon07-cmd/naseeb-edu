"""Booking window (next N days / date range), the longer list of meeting lengths, and Telegram messages for student changes."""
from datetime import timedelta

from django.utils import timezone

from apps.telegram_bot.models import StudentTelegram, TelegramLink, TelegramOutbox

from ..meetings import SCHEDULE_DAYS, outside_window
from ..models import Booking, MeetingAvailability, MeetingSchedule
from .base import RoleIsolationBase

URL = '/api/bookings/availability/weekly/'
EVERY_DAY = {str(day): [['09:00', '10:30']] for day in range(7)}


def tashkent_day(moment):
    return timezone.localtime(moment).date()


class WindowTestBase(RoleIsolationBase):
    def save(self, **fields):
        body = {'duration_minutes': 45, 'hours': EVERY_DAY, **fields}
        return self.client.put(URL, body, format='json')

    def slots(self):
        return MeetingAvailability.objects.filter(participant=self.counselor)

    def days(self):
        return sorted({tashkent_day(slot.starts_at) for slot in self.slots()})

    def offered(self, user=None):
        self.client.force_authenticate(user or self.student_a_user)
        return self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}').data


class WindowGenerationTests(WindowTestBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.client.force_authenticate(self.counselor)

    def test_rolling_window_generates_only_the_next_n_days(self):
        self.assertEqual(self.save(window_days=10).status_code, 200)
        self.assertLessEqual(self.days()[-1], self.today + timedelta(days=10))
        self.assertGreaterEqual(self.days()[-1], self.today + timedelta(days=10))
        self.assertEqual(MeetingSchedule.objects.get().generated_until, self.today + timedelta(days=10))

    def test_a_long_window_is_generated_up_to_the_horizon_and_topped_up_to_its_end(self):
        self.assertEqual(self.save(window_days=120).status_code, 200)
        self.assertEqual(self.days()[-1], self.today + timedelta(days=SCHEDULE_DAYS))
        MeetingSchedule.objects.update(generated_until=self.today + timedelta(days=10))
        self.offered()
        self.assertEqual(MeetingSchedule.objects.get().generated_until, self.today + timedelta(days=SCHEDULE_DAYS))
        # Time passes: the horizon moves but never beyond the window's own end.
        MeetingSchedule.objects.update(window_days=SCHEDULE_DAYS + 3, generated_until=self.today + timedelta(days=20))
        self.offered()
        self.assertEqual(MeetingSchedule.objects.get().generated_until, self.today + timedelta(days=SCHEDULE_DAYS))
        self.assertLessEqual(self.days()[-1], self.today + timedelta(days=SCHEDULE_DAYS + 3))

    def test_shrinking_the_window_removes_unbooked_slots_beyond_it_and_keeps_booked_and_manual_ones(self):
        self.save(window_days=30)
        late = self.slots().filter(starts_at__gt=timezone.now() + timedelta(days=25)).first()
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=late, topic='Essay',
                               starts_at=late.starts_at, duration_minutes=45)
        manual = MeetingAvailability.objects.create(
            participant=self.counselor, starts_at=(timezone.now() + timedelta(days=28)).replace(hour=15, minute=0, second=0, microsecond=0),
            duration_minutes=30,
        )
        self.assertEqual(self.save(window_days=5).status_code, 200)
        beyond = self.slots().filter(starts_at__gte=timezone.now() + timedelta(days=7))
        self.assertEqual(set(beyond.values_list('id', flat=True)), {late.id, manual.id})
        self.assertLessEqual(max(tashkent_day(slot.starts_at) for slot in self.slots().exclude(id__in=[late.id, manual.id])),
                             self.today + timedelta(days=5))

    def test_range_window_covers_only_those_dates(self):
        start, end = self.today + timedelta(days=5), self.today + timedelta(days=9)
        response = self.save(window_mode='range', window_start=start.isoformat(), window_end=end.isoformat())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((self.days()[0], self.days()[-1]), (start, end))
        self.assertEqual(len(self.days()), 5)
        # Topping up never goes past the end.
        self.offered()
        self.assertEqual(self.days()[-1], end)
        self.assertEqual(MeetingSchedule.objects.get().generated_until, end)

    def test_range_starting_in_the_past_begins_today(self):
        end = self.today + timedelta(days=3)
        self.save(window_mode='range', window_start=(self.today - timedelta(days=10)).isoformat(), window_end=end.isoformat())
        self.assertGreaterEqual(self.days()[0], self.today)
        self.assertEqual(self.days()[-1], end)

    def test_range_validation(self):
        today = self.today
        bad = [
            {'window_mode': 'range'},
            {'window_mode': 'range', 'window_start': today.isoformat()},
            {'window_mode': 'range', 'window_start': (today + timedelta(days=5)).isoformat(), 'window_end': (today + timedelta(days=2)).isoformat()},
            {'window_mode': 'range', 'window_start': (today - timedelta(days=5)).isoformat(), 'window_end': (today - timedelta(days=1)).isoformat()},
            {'window_mode': 'weekly'},
            {'window_days': 0},
            {'window_days': 366},
            {'window_mode': 'range', 'window_start': 'soon', 'window_end': 'later'},
        ]
        for fields in bad:
            response = self.save(**fields)
            self.assertEqual(response.status_code, 400, fields)
        self.assertFalse(MeetingSchedule.objects.exists())
        # A range of a single day, ending today, is fine.
        ok = self.save(window_mode='range', window_start=today.isoformat(), window_end=today.isoformat())
        self.assertEqual(ok.status_code, 200, ok.data)

    def test_old_clients_that_omit_the_window_keep_it(self):
        self.save(window_days=14)
        response = self.client.put(URL, {'duration_minutes': 30, 'hours': EVERY_DAY}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['window_mode'], response.data['window_days']), ('rolling', 14))
        self.assertEqual(self.days()[-1], self.today + timedelta(days=14))
        # Only the window days, nothing else, can be sent too.
        self.assertEqual(self.client.put(URL, {'window_days': 20}, format='json').status_code, 200)

    def test_get_reports_the_window_the_clock_and_the_tally(self):
        self.save(window_days=7)
        free = self.slots().filter(starts_at__gt=timezone.now()).count()
        booked = self.slots().filter(starts_at__gt=timezone.now() + timedelta(days=2)).first()
        Booking.objects.create(student=self.student_a, participant=self.counselor, availability_slot=booked, topic='Essay',
                               starts_at=booked.starts_at, duration_minutes=45)
        # Cancelled and past meetings are not part of the tally.
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Old', status='cancelled',
                               starts_at=timezone.now() + timedelta(days=3), duration_minutes=45)
        data = self.client.get(URL).data
        self.assertEqual(data['timezone'], 'Asia/Tashkent')
        self.assertEqual((data['window_mode'], data['window_days']), ('rolling', 7))
        self.assertEqual((data['upcoming_booked'], data['free_slots']), (1, free - 1))


class StudentListingTests(WindowTestBase):
    def test_students_do_not_see_slots_outside_the_window_or_inside_the_notice(self):
        self.client.force_authenticate(self.counselor)
        self.save(window_days=3)
        self.assertEqual(MeetingSchedule.objects.update(min_notice_hours=0), 1)
        # Hand-added slots the window would not have generated.
        far = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(days=20), duration_minutes=30)
        soon = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(hours=2), duration_minutes=30)
        MeetingSchedule.objects.update(min_notice_hours=24)
        ids = {row['id'] for row in self.offered()}
        self.assertTrue(ids)
        self.assertNotIn(far.id, ids)
        self.assertNotIn(soon.id, ids)
        self.assertTrue(all(tashkent_day(slot.starts_at) <= timezone.localdate() + timedelta(days=3)
                            for slot in self.slots().filter(id__in=ids)))
        # The all-staff overview applies the same rule.
        self.client.force_authenticate(self.student_a_user)
        overview = {row['id'] for row in self.client.get('/api/bookings/availability/').data}
        self.assertNotIn(far.id, overview)
        # The staff member's own list still shows everything they added.
        self.client.force_authenticate(self.counselor)
        self.assertIn(far.id, {row['id'] for row in self.client.get('/api/bookings/availability/').data})

    def test_a_student_cannot_book_or_move_to_a_slot_outside_the_window(self):
        MeetingSchedule.objects.create(participant=self.counselor, window_days=3, min_notice_hours=0)
        far = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(days=20), duration_minutes=30)
        near = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(days=1), duration_minutes=30)
        self.assertTrue(outside_window(self.counselor.id, far.starts_at))
        self.assertFalse(outside_window(self.counselor.id, near.starts_at))
        self.client.force_authenticate(self.student_a_user)

        def post(slot):
            return self.client.post('/api/bookings/', {
                'participant': self.counselor.id, 'topic': 'x', 'starts_at': slot.starts_at.isoformat(),
                'duration_minutes': 30, 'availability_slot': slot.id,
            }, format='json')
        refused = post(far)
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertIn('availability_slot', refused.data)
        booking = post(near)
        self.assertEqual(booking.status_code, 201, booking.data)
        moved = self.client.post(f'/api/bookings/{booking.data["id"]}/reschedule/', {
            'starts_at': far.starts_at.isoformat(), 'duration_minutes': 30, 'availability_slot': far.id,
        }, format='json')
        self.assertEqual(moved.status_code, 400, moved.data)

    def test_staff_without_a_schedule_are_not_limited(self):
        far = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(days=80), duration_minutes=30)
        self.assertFalse(outside_window(self.counselor.id, far.starts_at))
        self.assertIn(far.id, {row['id'] for row in self.offered()})


class MeetingLengthTests(WindowTestBase):
    def test_new_lengths_are_accepted_and_others_refused(self):
        self.client.force_authenticate(self.counselor)
        for minutes in (15, 20, 30, 45, 60, 90):
            response = self.save(duration_minutes=minutes, hours={'0': [['09:00', '12:00']]})
            self.assertEqual(response.status_code, 200, (minutes, response.data))
            self.assertEqual(response.data['duration_minutes'], minutes)
            self.assertEqual({slot.duration_minutes for slot in self.slots()}, {minutes})
        for minutes in (10, 25, 120):
            self.assertEqual(self.save(duration_minutes=minutes).status_code, 400, minutes)

    def test_a_ninety_minute_meeting_blocks_a_slot_that_starts_inside_it(self):
        start = (timezone.now() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Long', starts_at=start,
                               duration_minutes=90, status='approved')
        inside = MeetingAvailability.objects.create(participant=self.counselor, starts_at=start + timedelta(minutes=80), duration_minutes=15)
        after = MeetingAvailability.objects.create(participant=self.counselor, starts_at=start + timedelta(minutes=90), duration_minutes=15)
        MeetingSchedule.objects.create(participant=self.counselor, min_notice_hours=0)
        ids = {row['id'] for row in self.offered()}
        self.assertNotIn(inside.id, ids)
        self.assertIn(after.id, ids)

    def test_a_staff_invitation_may_be_ninety_minutes(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/', {
            'student': self.student_a.pk, 'topic': 'Long', 'duration_minutes': 90,
            'starts_at': (timezone.now() + timedelta(days=2)).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)


class TelegramMessageTests(WindowTestBase):
    """A student's own change reaches the student (confirmation) and their counselor (update), never anyone else."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.counselor)
        self.save(window_days=14, hours={str(day): [['09:00', '12:00']] for day in range(7)})
        MeetingSchedule.objects.update(min_notice_hours=0)
        self.slot = self.slots().filter(starts_at__gt=timezone.now() + timedelta(days=2)).first()
        self.other_slot = self.slots().filter(starts_at__gt=timezone.now() + timedelta(days=4)).first()
        self.student_chat, self.counselor_chat = 7001, 7002
        StudentTelegram.objects.create(user=self.student_a_user, chat_id=self.student_chat, language='en')
        self.link = TelegramLink.objects.create(user=self.counselor, chat_id=self.counselor_chat, language='en', auth_fingerprint='x')

    def act(self, user, method, path, body=None):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            return getattr(self.client, method)(path, body or {}, format='json')

    def book(self, slot=None):
        slot = slot or self.slot
        return self.act(self.student_a_user, 'post', '/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Essay <draft>', 'starts_at': slot.starts_at.isoformat(),
            'duration_minutes': slot.duration_minutes, 'availability_slot': slot.id,
        })

    def texts(self, chat):
        return [row.text for row in TelegramOutbox.objects.filter(chat_id=chat).order_by('id')]

    def test_booking_confirms_to_the_student_and_tells_the_counselor_with_the_tally(self):
        response = self.book()
        self.assertEqual(response.status_code, 201, response.data)
        (mine,) = self.texts(self.student_chat)
        self.assertIn('Booked', mine)
        self.assertIn('Tashkent', mine)
        self.assertIn('45 min', mine)
        self.assertIn('waiting for confirmation', mine)
        (theirs,) = self.texts(self.counselor_chat)
        self.assertIn('booked a meeting', theirs)
        self.assertIn(self.student_a_user.get_full_name() or self.student_a_user.username, theirs)
        self.assertIn('Essay &lt;draft&gt;', theirs)
        self.assertIn('45 min', theirs)
        self.assertIn('This window: 1 booked', theirs)
        self.assertRegex(theirs, r'· \d+ free slots left')

    def test_cancelling_frees_the_slot_and_messages_both_sides(self):
        booking_id = self.book().data['id']
        TelegramOutbox.objects.all().delete()
        response = self.act(self.student_a_user, 'post', f'/api/bookings/{booking_id}/cancel/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'cancelled')
        (mine,) = self.texts(self.student_chat)
        self.assertIn('You cancelled your meeting', mine)
        self.assertEqual(response.data['cancelled_by_role'], 'student')
        (theirs,) = self.texts(self.counselor_chat)
        self.assertIn('cancelled a meeting', theirs)
        self.assertIn('This window: 0 booked', theirs)
        # The slot is bookable again.
        self.assertIn(self.slot.id, {row['id'] for row in self.offered()})

    def test_rescheduling_messages_both_sides(self):
        booking_id = self.book().data['id']
        TelegramOutbox.objects.all().delete()
        response = self.act(self.student_a_user, 'post', f'/api/bookings/{booking_id}/reschedule/', {
            'starts_at': self.other_slot.starts_at.isoformat(), 'duration_minutes': self.other_slot.duration_minutes,
            'availability_slot': self.other_slot.id,
        })
        self.assertEqual(response.status_code, 200, response.data)
        (mine,) = self.texts(self.student_chat)
        self.assertIn('You asked to move', mine)
        self.assertIn('waiting for confirmation', mine)
        (theirs,) = self.texts(self.counselor_chat)
        self.assertIn('asked to move a meeting', theirs)

    def test_answering_an_invitation_tells_only_the_counselor(self):
        self.client.force_authenticate(self.counselor)
        start = (timezone.now() + timedelta(days=6)).replace(minute=0, second=0, microsecond=0)
        booking_id = self.act(self.counselor, 'post', '/api/bookings/', {
            'student': self.student_a.pk, 'topic': 'Plan', 'starts_at': start.isoformat(), 'duration_minutes': 30,
        }).data['id']
        # The student heard of the invitation; the counselor, who sent it, did not message themselves.
        self.assertEqual(len(self.texts(self.student_chat)), 1)
        self.assertEqual(self.texts(self.counselor_chat), [])
        self.act(self.student_a_user, 'post', f'/api/bookings/{booking_id}/approve/')
        self.assertEqual(len(self.texts(self.student_chat)), 1)
        (theirs,) = self.texts(self.counselor_chat)
        self.assertIn('accepted your invitation', theirs)
        declined = self.act(self.counselor, 'post', '/api/bookings/', {
            'student': self.student_a.pk, 'topic': 'Plan 2', 'starts_at': (start + timedelta(days=1)).isoformat(), 'duration_minutes': 30,
        }).data['id']
        self.act(self.student_a_user, 'post', f'/api/bookings/{declined}/reject/')
        self.assertIn('declined your invitation', self.texts(self.counselor_chat)[-1])

    def test_counselor_actions_do_not_message_the_counselor(self):
        booking_id = self.book().data['id']
        TelegramOutbox.objects.all().delete()
        self.act(self.counselor, 'post', f'/api/bookings/{booking_id}/approve/')
        staff = self.act(self.counselor, 'post', f'/api/bookings/{booking_id}/cancel/')
        self.assertEqual(staff.data['cancelled_by_role'], 'staff')
        self.assertEqual(self.texts(self.counselor_chat), [])
        # The student hears of the counselor's changes as before.
        self.assertEqual(len(self.texts(self.student_chat)), 2)

    def test_the_counselors_language_is_used(self):
        TelegramLink.objects.update(language='ru')
        self.book()
        self.assertIn('Ташкент', self.texts(self.counselor_chat)[0])
        self.assertIn('В этом окне', self.texts(self.counselor_chat)[0])

    def test_nothing_is_queued_for_unlinked_or_inactive_chats(self):
        StudentTelegram.objects.update(is_active=False)
        TelegramLink.objects.update(is_active=False)
        self.assertEqual(self.book().status_code, 201)
        self.assertFalse(TelegramOutbox.objects.exists())
        StudentTelegram.objects.all().delete()
        TelegramLink.objects.all().delete()
        self.assertEqual(self.book(self.other_slot).status_code, 201)
        self.assertFalse(TelegramOutbox.objects.exists())

    def test_only_the_bookings_participant_is_messaged(self):
        TelegramLink.objects.create(user=self.counselor_b, chat_id=7003, language='en', auth_fingerprint='x')
        TelegramLink.objects.create(user=self.teacher, chat_id=7004, language='en', auth_fingerprint='x')
        self.book()
        self.assertEqual(self.texts(7003), [])
        self.assertEqual(self.texts(7004), [])
        self.assertEqual(len(self.texts(self.counselor_chat)), 1)
