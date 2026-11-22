"""The counselor's post-meeting follow-up: queued ten minutes after the start, Done / Canceled, the note."""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking
from apps.telegram_bot import followup, student_link
from apps.telegram_bot.models import PendingMeetingNote, TelegramLink, TelegramOutbox

from .base import KEY, BotTestCase

STAFF_CHAT = 920002
OTHER_CHAT = 920003
HEADERS = {'HTTP_X_BOT_SERVICE_KEY': KEY}


@override_settings(BOT_SERVICE_KEY=KEY, FRONTEND_URL='https://app.example.com')
class FollowupTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)

    def booking(self, status=Booking.Status.APPROVED, participant=None):
        return Booking.objects.create(
            student=self.s1, participant=participant or self.c1, topic='Plan', starts_at=self.start,
            duration_minutes=45, status=status,
        )

    def link(self, user=None, chat=STAFF_CHAT, language='en', **extra):
        return TelegramLink.objects.create(
            user=user or self.c1, chat_id=chat, language=language, auth_fingerprint=self.fingerprint(user or self.c1), **extra,
        )

    def fingerprint(self, user):
        from apps.telegram_bot.services import fingerprint
        return fingerprint(user)

    def rows(self):
        return TelegramOutbox.objects.filter(key__contains=':followup:')

    def moment(self, minutes):
        return self.start + timedelta(minutes=minutes)

    def post(self, path, **body):
        return self.client.post(f'/api/bot/{path}/', body, format='json', **HEADERS)

    def press(self, booking, action, chat=STAFF_CHAT):
        return self.post('meeting-followup', chat_id=chat, booking_id=booking.pk, action=action)

    # --- queueing ---

    def test_queued_once_at_start_plus_ten_minutes(self):
        booking = self.booking()
        self.link()
        self.assertEqual(student_link.queue_followups(self.moment(9)), 0)
        self.assertEqual(student_link.queue_followups(self.moment(10)), 1)
        row = self.rows().get()
        self.assertEqual(row.key, f'meeting:{booking.pk}:{int(self.start.timestamp())}:followup:staff')
        self.assertEqual(row.chat_id, STAFF_CHAT)
        self.assertIn('Stu1 Tester', row.text)
        self.assertEqual([b['callback_data'] for b in row.buttons[0]], [f'mf:done:{booking.pk}', f'mf:cancel:{booking.pk}'])
        self.assertTrue(all(len(b['callback_data'].encode()) <= 64 for b in row.buttons[0]))

    def test_idempotent_across_repeated_runs(self):
        self.booking()
        self.link()
        self.assertEqual(student_link.queue_followups(self.moment(10)), 1)
        self.assertEqual(student_link.queue_followups(self.moment(11)), 0)
        student_link.pending_messages(self.moment(12))
        student_link.pending_messages(self.moment(13))
        self.assertEqual(self.rows().count(), 1)

    def test_sent_row_is_not_requeued(self):
        self.booking()
        self.link()
        student_link.pending_messages(self.moment(10))
        TelegramOutbox.objects.update(sent_at=self.moment(10))
        student_link.pending_messages(self.moment(20))
        self.assertEqual(self.rows().count(), 1)

    def test_not_for_unapproved_meetings(self):
        self.link()
        for status in (Booking.Status.PENDING, Booking.Status.CANCELLED, Booking.Status.REJECTED, Booking.Status.COMPLETED):
            Booking.objects.all().delete()
            self.booking(status)
            self.assertEqual(student_link.queue_followups(self.moment(10)), 0, status)

    def test_not_for_counselors_without_an_active_link(self):
        self.booking()
        self.assertEqual(student_link.queue_followups(self.moment(10)), 0)
        self.link(is_active=False)
        self.assertEqual(student_link.queue_followups(self.moment(10)), 0)

    def test_too_late_is_skipped_and_a_moved_meeting_is_followed_up_again(self):
        booking = self.booking()
        self.link()
        self.assertEqual(student_link.queue_followups(self.moment(10 + 61)), 0)
        student_link.queue_followups(self.moment(10))
        booking.starts_at += timedelta(days=1)
        booking.save()
        student_link.queue_followups(booking.starts_at + timedelta(minutes=10))
        self.assertEqual(self.rows().count(), 2)

    def test_unsent_followup_is_dropped_if_the_meeting_is_no_longer_approved(self):
        booking = self.booking()
        self.link()
        student_link.queue_followups(self.moment(10))
        booking.status = Booking.Status.CANCELLED
        booking.save()
        self.assertEqual(student_link.pending_messages(self.moment(11))['messages'], [])

    def test_followup_text_is_in_the_link_language(self):
        self.booking()
        self.link(language='ru')
        student_link.queue_followups(self.moment(10))
        self.assertIn('Как прошла встреча', self.rows().get().text)
        self.assertEqual(self.rows().get().buttons[0][0]['text'], '✅ Состоялась')

    # --- buttons ---

    def test_done_completes_the_meeting_and_the_portal_serializer_shows_it(self):
        booking = self.booking()
        self.link()
        response = self.press(booking, 'done')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['result'], 'done')
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.client.force_authenticate(self.c1)
        data = self.client.get(f'/api/bookings/{booking.pk}/').data
        self.assertEqual(data['status'], 'completed')

    def test_cancel_marks_cancelled_by_staff_and_asks_for_a_note(self):
        booking = self.booking()
        self.link()
        response = self.press(booking, 'cancel')
        self.assertEqual(response.data['result'], 'done')
        self.assertTrue(response.data['prompt'])
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.cancelled_by_role), (Booking.Status.CANCELLED, 'staff'))
        self.assertTrue(PendingMeetingNote.objects.filter(chat_id=STAFF_CHAT, booking=booking).exists())

    def test_note_is_saved_once_and_visible_to_staff_but_not_the_student(self):
        booking = self.booking()
        self.link()
        self.press(booking, 'cancel')
        response = self.post('meeting-note', chat_id=STAFF_CHAT, text='  Student was ill  ')
        self.assertEqual(response.data['result'], 'saved')
        booking.refresh_from_db()
        self.assertEqual(booking.staff_note, 'Student was ill')
        self.assertFalse(PendingMeetingNote.objects.exists())
        # A second text is not a note any more.
        self.assertEqual(self.post('meeting-note', chat_id=STAFF_CHAT, text='more').data['result'], 'none')
        booking.refresh_from_db()
        self.assertEqual(booking.staff_note, 'Student was ill')
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.get(f'/api/bookings/{booking.pk}/').data['staff_note'], 'Student was ill')
        self.client.force_authenticate(self.s1.user)
        self.assertNotIn('staff_note', self.client.get(f'/api/bookings/{booking.pk}/').data)

    def test_note_with_no_pending_cancel_is_not_saved(self):
        booking = self.booking()
        self.link()
        self.assertEqual(self.post('meeting-note', chat_id=STAFF_CHAT, text='hello').data['result'], 'none')
        booking.refresh_from_db()
        self.assertEqual(booking.staff_note, '')

    def test_note_for_an_unknown_chat_is_refused(self):
        response = self.post('meeting-note', chat_id=OTHER_CHAT, text='hello')
        self.assertEqual(response.status_code, 404)

    def test_expired_note_wait_saves_nothing(self):
        booking = self.booking()
        self.link()
        self.press(booking, 'cancel')
        PendingMeetingNote.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.post('meeting-note', chat_id=STAFF_CHAT, text='late').data['result'], 'none')
        booking.refresh_from_db()
        self.assertEqual(booking.staff_note, '')
        self.assertFalse(PendingMeetingNote.objects.exists())

    def test_double_tap_does_not_change_anything_twice(self):
        booking = self.booking()
        self.link()
        self.press(booking, 'done')
        again = self.press(booking, 'done')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['result'], 'already')
        self.assertTrue(again.data['alert'])
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_double_cancel_tap_reasks_the_note_without_a_second_cancel(self):
        booking = self.booking()
        self.link()
        self.press(booking, 'cancel')
        updated = Booking.objects.get(pk=booking.pk).updated_at
        again = self.press(booking, 'cancel')
        self.assertEqual(again.data['result'], 'already')
        self.assertTrue(again.data['prompt'])
        self.assertEqual(Booking.objects.get(pk=booking.pk).updated_at, updated)
        self.assertEqual(PendingMeetingNote.objects.count(), 1)

    def test_status_changed_on_the_web_is_not_overwritten(self):
        booking = self.booking(Booking.Status.CANCELLED)
        booking.cancelled_by_role = 'student'
        booking.save()
        self.link()
        for action in ('done', 'cancel'):
            response = self.press(booking, action)
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.data['result'], ('already', 'unavailable'))
            self.assertIn('cancelled', response.data['alert'])
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.cancelled_by_role), (Booking.Status.CANCELLED, 'student'))
        self.assertFalse(PendingMeetingNote.objects.exists())
        completed = self.booking(Booking.Status.COMPLETED)
        response = self.press(completed, 'cancel')
        self.assertEqual(response.data['result'], 'unavailable')
        completed.refresh_from_db()
        self.assertEqual(completed.status, Booking.Status.COMPLETED)

    def test_another_counselors_chat_is_rejected(self):
        booking = self.booking()
        self.link()
        self.link(user=self.c2, chat=OTHER_CHAT)
        for action in ('done', 'cancel'):
            self.assertEqual(self.press(booking, action, chat=OTHER_CHAT).status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.APPROVED)
        self.assertFalse(PendingMeetingNote.objects.exists())

    def test_unlinked_chat_and_bad_input_are_refused(self):
        booking = self.booking()
        self.assertEqual(self.press(booking, 'done', chat=777).status_code, 404)
        self.link()
        self.assertEqual(self.post('meeting-followup', chat_id=STAFF_CHAT, booking_id=booking.pk, action='x').status_code, 400)
        self.assertEqual(self.post('meeting-followup', chat_id=STAFF_CHAT, booking_id='1', action='done').status_code, 400)
        self.assertEqual(self.client.post('/api/bot/meeting-followup/', {}, format='json').status_code, 401)

    # --- revoked links ---

    def revoke(self, how):
        if how == 'password':
            self.c1.password_version += 1
            self.c1.save(update_fields=['password_version'])
        else:
            self.c1.is_active = False
            self.c1.save(update_fields=['is_active'])

    def check_revoked(self, how):
        self.booking()
        self.link()
        self.revoke(how)
        self.assertEqual(student_link.queue_followups(self.moment(10)), 0, how)
        self.assertEqual(student_link.queue_reminders(self.start - timedelta(minutes=60)), 0, how)
        self.assertFalse(TelegramOutbox.objects.exists(), how)

    def test_password_change_stops_followups_and_reminders(self):
        self.check_revoked('password')

    def test_deactivated_account_stops_followups_and_reminders(self):
        self.check_revoked('deactivated')

    def test_an_already_queued_row_is_not_delivered_after_the_link_is_revoked(self):
        self.booking()
        self.link()
        student_link.queue_followups(self.moment(10))
        # The start reminder (step 0) is still within its grace at start+10, so pick the follow-up by its buttons.
        self.assertEqual(len(self.followups(student_link.pending_messages(self.moment(10))['messages'])), 1)
        TelegramOutbox.objects.update(claimed_at=None)
        self.revoke('password')
        self.assertEqual(student_link.pending_messages(self.moment(11))['messages'], [])
        self.assertFalse(TelegramOutbox.objects.exists())

    @staticmethod
    def followups(messages):
        return [m for m in messages if any(b.get('callback_data', '').startswith('mf:') for row in m['buttons'] for b in row)]

    # --- dismissing the note ---

    def test_dismiss_forgets_the_pending_note(self):
        booking = self.booking()
        self.link()
        self.press(booking, 'cancel')
        self.assertTrue(self.post('meeting-note', chat_id=STAFF_CHAT, dismiss=True).data['dismissed'])
        self.assertFalse(PendingMeetingNote.objects.exists())
        self.assertEqual(self.post('meeting-note', chat_id=STAFF_CHAT, text='Ali ali@x.com +998901234567').data['result'], 'none')
        booking.refresh_from_db()
        self.assertEqual(booking.staff_note, '')
        self.assertFalse(self.post('meeting-note', chat_id=STAFF_CHAT, dismiss=True).data['dismissed'])

    def test_followup_module_constants(self):
        self.assertEqual(followup.FOLLOWUP_DELAY, timedelta(minutes=10))
