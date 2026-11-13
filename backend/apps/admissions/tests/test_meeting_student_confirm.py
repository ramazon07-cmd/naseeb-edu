from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from apps.telegram_bot.models import StudentTelegram, TelegramOutbox

from ..models import Booking, MeetingAvailability, MeetingSchedule, Notification
from .base import RoleIsolationBase


def hour(offset_hours=0, days=0):
    return (timezone.now() + timedelta(days=days, hours=offset_hours)).replace(minute=0, second=0, microsecond=0)


class StaffInvitationTests(RoleIsolationBase):
    """A counselor's booking waits for the student; only the student can confirm or decline it."""

    def setUp(self):
        super().setUp()
        for user in (self.student_a_user, self.counselor):
            user.google_email = f'{user.username}@gmail.com'
            user.save(update_fields=['google_email'])
        StudentTelegram.objects.create(user=self.student_a_user, chat_id=4242)
        self.start = hour(days=3)

    def invite(self, **extra):
        self.client.force_authenticate(self.counselor)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/bookings/', {
                'student': self.student_a.pk, 'topic': 'College list', 'starts_at': self.start.isoformat(),
                'duration_minutes': 45, **extra,
            }, format='json')
        return response

    def answer(self, user, booking_id, verb):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/api/bookings/{booking_id}/{verb}/')

    def test_staff_booking_is_pending_for_the_student_and_notifies_every_channel(self):
        response = self.invite()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['status'], response.data['staff_requested']), ('pending', True))
        notice = Notification.objects.get(student=self.student_a, title='Meeting invitation')
        self.assertIn('invited you to "College list"', notice.message)
        self.assertIn('Confirm it on the website', notice.message)
        self.assertEqual([m.to for m in mail.outbox], [['student-a@gmail.com']])
        outbox = TelegramOutbox.objects.get()
        self.assertEqual(outbox.chat_id, 4242)
        self.assertIn('College list', outbox.text)

    def test_ask_student_false_confirms_at_once(self):
        response = self.invite(ask_student=False)
        self.assertEqual((response.data['status'], response.data['staff_requested']), ('approved', False))
        self.assertTrue(Notification.objects.filter(student=self.student_a, title='Meeting confirmed').exists())
        self.assertFalse(Notification.objects.filter(title='Meeting invitation').exists())

    def test_student_confirms_and_counselor_is_told(self):
        booking_id = self.invite().data['id']
        mail.outbox.clear()
        response = self.answer(self.student_a_user, booking_id, 'approve')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'approved')
        notice = Notification.objects.get(recipient=self.counselor, title='Meeting invitation accepted')
        self.assertIn('confirmed', notice.message)
        self.assertEqual([m.to for m in mail.outbox], [['counselor-test@gmail.com']])
        # The counselor is told; the student is not messaged about their own answer.
        self.assertEqual(TelegramOutbox.objects.count(), 1)

    def test_student_declines(self):
        booking_id = self.invite().data['id']
        response = self.answer(self.student_a_user, booking_id, 'reject')
        self.assertEqual(response.data['status'], 'rejected')
        self.assertTrue(Notification.objects.filter(recipient=self.counselor, title='Meeting invitation declined').exists())
        # The time is free again.
        self.assertEqual(self.invite().status_code, 201)

    def test_counselor_cannot_approve_or_reject_their_own_invitation(self):
        booking_id = self.invite().data['id']
        for verb in ('approve', 'reject'):
            self.assertEqual(self.answer(self.counselor, booking_id, verb).status_code, 403)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, 'pending')
        # They can cancel it.
        self.assertEqual(self.answer(self.counselor, booking_id, 'cancel').status_code, 200)

    def test_other_students_and_student_requests_keep_their_rules(self):
        booking_id = self.invite().data['id']
        self.assertEqual(self.answer(self.student_b_user, booking_id, 'approve').status_code, 404)
        own = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Mine', starts_at=hour(days=5), duration_minutes=45,
        )
        # A student's own request is still answered by the staff member only.
        self.assertEqual(self.answer(self.student_a_user, own.pk, 'approve').status_code, 403)
        self.assertEqual(self.answer(self.counselor, own.pk, 'approve').status_code, 200)

    def test_expired_invitation_cannot_be_confirmed(self):
        booking = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Old', starts_at=timezone.now() - timedelta(hours=1),
            duration_minutes=45, staff_requested=True,
        )
        self.assertTrue(booking.is_expired)
        self.assertEqual(self.answer(self.student_a_user, booking.pk, 'approve').status_code, 400)

    def test_student_move_hands_the_decision_to_the_counselor(self):
        booking_id = self.invite().data['id']
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=hour(days=6), duration_minutes=45)
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(f'/api/bookings/{booking_id}/reschedule/', {
            'starts_at': slot.starts_at.isoformat(), 'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['status'], response.data['staff_requested']), ('pending', False))

    def test_counselor_move_keeps_waiting_for_the_student(self):
        booking_id = self.invite().data['id']
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/bookings/{booking_id}/reschedule/', {
            'starts_at': hour(days=4).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['status'], response.data['staff_requested']), ('pending', True))

    def test_booking_a_free_slot_consumes_it(self):
        slot = MeetingAvailability.objects.create(participant=self.counselor, starts_at=self.start, duration_minutes=45)
        booking = Booking.objects.get(pk=self.invite().data['id'])
        self.assertEqual(booking.availability_slot_id, slot.id)
        # No other student can take the time any more.
        self.client.force_authenticate(self.student_b_user)
        self.assertEqual(self.client.get('/api/bookings/availability/').status_code, 200)
        self.client.force_authenticate(self.student_a_user)
        listed = self.client.get(f'/api/bookings/availability/?participant={self.counselor.id}').data
        self.assertNotIn(slot.id, [row['id'] for row in listed])
        posted = self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'x', 'starts_at': slot.starts_at.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(posted.status_code, 400)

    def test_overlap_and_cross_school_are_refused(self):
        self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.invite().status_code, 400)
        self.client.force_authenticate(self.counselor)
        other = self.client.post('/api/bookings/', {
            'student': self.student_b.pk, 'topic': 'x', 'starts_at': hour(days=9).isoformat(), 'duration_minutes': 30,
        }, format='json')
        self.assertEqual(other.status_code, 400)
        self.assertFalse(Booking.objects.filter(student=self.student_b).exists())


class MinimumNoticeTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.soon = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(hours=5), duration_minutes=45)
        self.later = MeetingAvailability.objects.create(participant=self.counselor, starts_at=timezone.now() + timedelta(hours=30), duration_minutes=45)

    def ids(self, query=''):
        self.client.force_authenticate(self.student_a_user)
        return [row['id'] for row in self.client.get(f'/api/bookings/availability/{query}').data]

    def post(self, slot):
        self.client.force_authenticate(self.student_a_user)
        return self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Essay', 'starts_at': slot.starts_at.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')

    def set_notice(self, hours):
        MeetingSchedule.objects.update_or_create(participant=self.counselor, defaults={'min_notice_hours': hours})

    def test_default_twelve_hours_hides_and_refuses_near_slots(self):
        for query in ('', f'?participant={self.counselor.id}'):
            self.assertEqual(self.ids(query), [self.later.id])
        response = self.post(self.soon)
        self.assertEqual(response.status_code, 400)
        self.assertIn('availability_slot', response.data)
        self.assertEqual(self.post(self.later).status_code, 201)

    def test_notice_is_configurable_including_zero(self):
        self.set_notice(0)
        self.assertEqual(set(self.ids()), {self.soon.id, self.later.id})
        self.assertEqual(self.post(self.soon).status_code, 201)
        self.set_notice(48)
        self.assertEqual(self.ids(), [])
        self.assertEqual(self.post(self.later).status_code, 400)

    def test_student_reschedule_respects_notice_but_staff_do_not(self):
        booking = Booking.objects.get(pk=self.post(self.later).data['id'])
        self.client.force_authenticate(self.student_a_user)
        moved = self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': self.soon.starts_at.isoformat(), 'duration_minutes': 45, 'availability_slot': self.soon.id,
        }, format='json')
        self.assertEqual(moved.status_code, 400)
        self.assertEqual(self.ids(f'?reschedule={booking.pk}'), [self.later.id])
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/bookings/{booking.pk}/reschedule/', {
            'starts_at': self.soon.starts_at.isoformat(), 'duration_minutes': 45,
        }, format='json').status_code, 200)

    def test_staff_booking_ignores_notice(self):
        self.set_notice(168)
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/bookings/', {
            'student': self.student_a.pk, 'topic': 'Urgent', 'starts_at': (timezone.now() + timedelta(hours=2)).isoformat(),
            'duration_minutes': 30,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        # Staff still see every slot of their own.
        self.assertEqual(len(self.client.get('/api/bookings/availability/').data), 2)

    def test_weekly_hours_api_stores_and_validates_notice(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get('/api/bookings/availability/weekly/').data['min_notice_hours'], 12)
        saved = self.client.put('/api/bookings/availability/weekly/', {
            'duration_minutes': 45, 'hours': {'0': [['09:00', '12:00']]}, 'min_notice_hours': 24,
        }, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(MeetingSchedule.objects.get(participant=self.counselor).min_notice_hours, 24)
        for bad in (-1, 169):
            response = self.client.put('/api/bookings/availability/weekly/', {
                'duration_minutes': 45, 'hours': {}, 'min_notice_hours': bad,
            }, format='json')
            self.assertEqual(response.status_code, 400)


class BookMeetingsCommandTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.day = (timezone.localdate() + timedelta(days=3))
        self.book = f'student-a|{self.day} 09:45|45|Welcome meeting'

    def run_command(self, *args):
        out = StringIO()
        call_command('book_meetings', '--counselor', 'counselor-test', *args, stdout=out)
        return out.getvalue()

    def test_sets_schedule_and_invites_idempotently(self):
        weekday = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][self.day.weekday()]
        args = [
            '--weekly', f'{weekday}=09:00-00:00', '--from', str(self.day), '--to', str(self.day + timedelta(days=7)),
            '--notice-hours', '6', '--book', self.book,
        ]
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command(*args)
        schedule = MeetingSchedule.objects.get(participant=self.counselor)
        self.assertEqual((schedule.min_notice_hours, schedule.hours), (6, {str(self.day.weekday()): [['09:00', '00:00']]}))
        slots = MeetingAvailability.objects.filter(participant=self.counselor, from_schedule=True)
        self.assertTrue(slots.exists())
        booking = Booking.objects.get()
        self.assertEqual((booking.status, booking.staff_requested, booking.topic), ('pending', True, 'Welcome meeting'))
        self.assertIsNotNone(booking.availability_slot_id)
        self.assertEqual(Notification.objects.filter(title='Meeting invitation').count(), 1)
        count = slots.count()
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command(*args)
        self.assertEqual((Booking.objects.count(), slots.count()), (1, count))
        self.assertEqual(Notification.objects.filter(title='Meeting invitation').count(), 1)

    def test_midnight_end_reaches_the_last_slot_of_the_day(self):
        weekday = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][self.day.weekday()]
        self.run_command('--weekly', f'{weekday}=22:00-00:00', '--from', str(self.day), '--to', str(self.day))
        starts = [timezone.localtime(slot.starts_at).strftime('%H:%M') for slot in MeetingAvailability.objects.filter(participant=self.counselor)]
        self.assertEqual(starts, ['22:00', '22:45'])

    def test_refuses_students_the_counselor_cannot_see(self):
        with self.assertRaises(CommandError):
            self.run_command('--book', f'student-b|{self.day} 10:00|45|x')
        self.assertFalse(Booking.objects.exists())

    def test_dry_run_saves_and_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            output = self.run_command('--notice-hours', '3', '--book', self.book, '--dry-run')
        self.assertIn('Dry run', output)
        self.assertFalse(Booking.objects.exists() or Notification.objects.exists() or MeetingSchedule.objects.exists())

    def test_zone_conversion(self):
        # 09:00-12:00 Moscow is 11:00-14:00 in Tashkent (+2).
        weekday = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][self.day.weekday()]
        with override_settings(TIME_ZONE='Asia/Tashkent'):
            self.run_command('--weekly', f'{weekday}=09:00-12:00', '--tz', 'Europe/Moscow', '--from', str(self.day), '--to', str(self.day))
        hours = MeetingSchedule.objects.get(participant=self.counselor).hours
        self.assertEqual(hours, {str(self.day.weekday()): [['11:00', '14:00']]})
