from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking, MeetingAvailability
from apps.telegram_bot import meeting_cards, student_link
from apps.telegram_bot.models import StudentLinkToken, StudentTelegram, TelegramOutbox

from .base import BotTestCase

STAFF_CHAT = 7001
STUDENT_CHAT = 7002


def soon(days=3, hour=18):
    return (timezone.now() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


@override_settings(TELEGRAM_BOT_USERNAME='naseeb_test_bot', FRONTEND_URL='https://app.example.com')
class MeetingCardTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.staff_chat = self.link(self.c1, chat_id=STAFF_CHAT, language='en')
        self.tg = StudentTelegram.objects.create(
            user=self.s1.user, chat_id=STUDENT_CHAT, language='en', telegram_username='sardor_a',
        )
        self.slot = MeetingAvailability.objects.create(participant=self.c1, starts_at=soon(), duration_minutes=45)
        MeetingAvailability.objects.create(participant=self.c1, starts_at=soon(4), duration_minutes=45)
        self.booking = Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Essay', starts_at=soon(), duration_minutes=45,
            status='pending', availability_slot=self.slot,
        )

    def action(self, chat, action, booking=None, **extra):
        return self.post('meeting-action', {'chat_id': chat, 'booking_id': (booking or self.booking).pk, 'action': action, **extra})

    def outbox(self):
        return list(TelegramOutbox.objects.order_by('id'))

    # --- username ---------------------------------------------------------------------------

    def test_the_username_is_stored_when_the_student_links(self):
        self.tg.delete()
        token = student_link.issue_token(self.s2.user)['url'].split('start=s_', 1)[1]
        response = self.post('student-link', {'chat_id': 7100, 'token': token, 'language': 'en', 'telegram_username': '@Sardor_B'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(StudentTelegram.objects.get(user=self.s2.user).telegram_username, 'Sardor_B')
        self.assertFalse(StudentLinkToken.objects.exists())

    def test_a_bad_username_is_not_stored(self):
        self.assertEqual(student_link.clean_username('not valid!'), '')
        self.assertEqual(student_link.clean_username(None), '')

    # --- cards ------------------------------------------------------------------------------

    def test_the_counselor_card_for_a_student_request(self):
        student_link_queue = student_link  # noqa: F841 - the module is the public entry point
        from apps.telegram_bot.staff_meetings import queue_staff_update

        self.assertTrue(queue_staff_update(self.booking, 'booked'))
        message = self.outbox()[-1]
        lines = message.text.split('\n')
        self.assertEqual(lines[0], '📅 New meeting request')
        self.assertEqual(lines[1], '<b>Stu1 Tester</b>')
        self.assertRegex(lines[2], r'^\w{3} \d{1,2} \w{3}, \d{2}:00 \(Tashkent\) · 45 min$')
        self.assertEqual(lines[3], 'Telegram: @sardor_a')
        self.assertEqual(lines[4], 'Slots left: 1')
        callbacks = [b['callback_data'] for row in message.buttons for b in row if 'callback_data' in b]
        self.assertEqual(callbacks, [f'mt:confirm:{self.booking.pk}', f'mt:decline:{self.booking.pk}'])
        urls = [b['url'] for row in message.buttons for b in row if 'url' in b]
        self.assertEqual(urls, [f'https://app.example.com/students/{self.s1.pk}', 'https://t.me/sardor_a'])
        self.assertTrue(all(len(c.encode()) <= 64 for c in callbacks))

    def test_not_linked_and_no_username_lines(self):
        from apps.telegram_bot.staff_meetings import queue_staff_update

        self.tg.telegram_username = ''
        self.tg.save()
        queue_staff_update(self.booking, 'booked')
        self.assertIn('Telegram: linked, no username', self.outbox()[-1].text)
        self.assertEqual(len(self.outbox()[-1].buttons), 2)  # confirm/decline + profile only
        self.tg.delete()
        queue_staff_update(self.booking, 'booked')
        self.assertIn('Telegram: not linked', self.outbox()[-1].text)

    def test_counselor_buttons_follow_the_state(self):
        self.booking.status = 'approved'
        buttons = meeting_cards.buttons_for(self.booking, 'staff', 'en')
        self.assertEqual([b['callback_data'] for b in buttons[0]], [f'mt:cancel:{self.booking.pk}'])
        self.booking.status = 'cancelled'
        buttons = meeting_cards.buttons_for(self.booking, 'staff', 'en')
        self.assertTrue(all('callback_data' not in b for row in buttons for b in row))
        # A staff invitation waiting for the student can be cancelled but not confirmed by staff.
        self.booking.status, self.booking.staff_requested = 'pending', True
        buttons = meeting_cards.buttons_for(self.booking, 'staff', 'en')
        self.assertEqual([b['callback_data'] for b in buttons[0]], [f'mt:cancel:{self.booking.pk}'])

    @override_settings(FRONTEND_URL='http://localhost:5173')
    def test_url_buttons_need_https(self):
        buttons = meeting_cards.buttons_for(self.booking, 'staff', 'en')
        self.assertFalse(any('url' in b and b['url'].startswith('http://') for row in buttons for b in row))
        self.assertEqual(meeting_cards.buttons_for(self.booking, 'student', 'en'), [])

    def test_the_student_card_has_only_a_website_button(self):
        self.assertTrue(student_link.queue_own_action(self.booking, 'booked'))
        message = self.outbox()[-1]
        self.assertEqual(message.chat_id, STUDENT_CHAT)
        lines = message.text.split('\n')
        self.assertEqual(lines[0], '✅ Meeting requested')
        self.assertEqual(lines[1], '<b>Counselor1 Tester</b>')
        self.assertIn('(Tashkent) · 45 min', lines[2])
        self.assertEqual(lines[3], 'Status: waiting for confirmation')
        self.assertEqual(message.buttons, [[{'text': '🌐 Open on website', 'url': 'https://app.example.com/meetings'}]])

    def test_an_invitation_card_asks_for_the_website(self):
        self.booking.staff_requested = True
        self.booking.save()
        student_link.queue_event(self.booking, self.s1.user, 'invited')
        message = self.outbox()[-1]
        self.assertTrue(message.text.startswith('📅 Meeting invitation'))
        self.assertIn('Status: please confirm on the website', message.text)
        self.assertTrue(all('callback_data' not in b for row in message.buttons for b in row))

    def test_names_are_escaped(self):
        self.s1.user.first_name = '<b>Hack</b>'
        self.s1.user.save()
        self.booking.refresh_from_db()
        text = meeting_cards.staff_card(Booking.objects.get(pk=self.booking.pk), 'en', 'h_new')
        self.assertIn('&lt;b&gt;Hack&lt;/b&gt;', text)
        self.assertNotIn('<b>Hack', text)

    def test_the_outbox_endpoint_returns_buttons(self):
        from apps.telegram_bot.staff_meetings import queue_staff_update

        queue_staff_update(self.booking, 'booked')
        messages = self.post('student-outbox').json()['messages']
        self.assertEqual(len(messages[0]['buttons'][0]), 2)

    # --- actions ----------------------------------------------------------------------------

    def test_the_counselor_confirms_and_the_student_is_told(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.action(STAFF_CHAT, 'confirm')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['result'], 'done')
        self.assertTrue(data['text'].startswith('✅ Meeting confirmed'))
        self.assertTrue(data['text'].endswith('✅ Confirmed'))
        self.assertEqual([b['callback_data'] for b in data['buttons'][0]], [f'mt:cancel:{self.booking.pk}'])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'approved')
        card = TelegramOutbox.objects.get(chat_id=STUDENT_CHAT)
        self.assertIn('Status: confirmed', card.text)

    def test_the_counselor_declines(self):
        with self.captureOnCommitCallbacks(execute=True):
            data = self.action(STAFF_CHAT, 'decline').json()
        self.assertEqual(data['result'], 'done')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'rejected')
        self.assertTrue(TelegramOutbox.objects.filter(chat_id=STUDENT_CHAT, text__startswith='❌ Request declined').exists())

    def test_cancelling_frees_the_slot_and_records_who_did_it(self):
        self.booking.status = 'approved'
        self.booking.save()
        with self.captureOnCommitCallbacks(execute=True):
            data = self.action(STAFF_CHAT, 'cancel').json()
        self.assertTrue(data['text'].endswith('🚫 Cancelled by you'))
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.status, self.booking.cancelled_by_role), ('cancelled', 'staff'))
        self.assertFalse(self.slot.bookings.filter(status__in=Booking.OPEN_STATUSES).exists())
        self.assertTrue(TelegramOutbox.objects.filter(chat_id=STUDENT_CHAT, text__startswith='🚫 Meeting cancelled').exists())

    def test_pressing_twice_says_already_and_changes_nothing(self):
        self.action(STAFF_CHAT, 'confirm')
        data = self.action(STAFF_CHAT, 'confirm').json()
        self.assertEqual(data['result'], 'already')
        self.assertEqual(data['alert'], 'Already confirmed')
        self.assertTrue(data['text'].endswith('Already confirmed'))

    def test_a_started_or_closed_meeting_is_unavailable(self):
        Booking.objects.filter(pk=self.booking.pk).update(status='cancelled')
        data = self.action(STAFF_CHAT, 'confirm').json()
        self.assertEqual(data['result'], 'unavailable')
        self.assertEqual(data['buttons'][0][0].get('callback_data'), None)
        Booking.objects.filter(pk=self.booking.pk).update(status='approved', starts_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.action(STAFF_CHAT, 'cancel').json()['result'], 'unavailable')

    def test_another_counselor_in_the_same_school_cannot_act(self):
        other = self.link(self.c2, chat_id=7003)
        response = self.action(other, 'confirm')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Stu1', response.content.decode())
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')

    def test_a_counselor_of_another_school_cannot_act(self):
        other = self.link(self.cb, chat_id=7004)
        self.assertEqual(self.action(other, 'cancel').status_code, 404)

    def test_a_participant_who_moved_school_cannot_act(self):
        self.c1.school = self.school_b
        self.c1.save(update_fields=['school'])
        self.assertEqual(self.action(STAFF_CHAT, 'confirm').status_code, 404)

    def test_students_cannot_act_from_telegram(self):
        for action in ('confirm', 'decline', 'cancel'):
            response = self.action(STUDENT_CHAT, action)
            self.assertEqual(response.status_code, 403, action)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.status, self.booking.cancelled_by_role), ('pending', None))
        # A refused press still refreshes the username.
        self.action(STUDENT_CHAT, 'cancel', telegram_username='new_name')
        self.tg.refresh_from_db()
        self.assertEqual(self.tg.telegram_username, 'new_name')

    def test_unlinked_chats_and_bad_input_are_refused(self):
        self.assertEqual(self.action(999, 'confirm').status_code, 404)
        self.assertEqual(self.action(STAFF_CHAT, 'delete').status_code, 400)
        self.assertEqual(self.post('meeting-action', {'chat_id': STAFF_CHAT, 'booking_id': 'x', 'action': 'confirm'}).status_code, 400)
        self.assertEqual(self.post('meeting-action', {'chat_id': STAFF_CHAT, 'booking_id': 10 ** 9, 'action': 'confirm'}).status_code, 404)
        self.assertEqual(self.post('meeting-action', {'chat_id': STAFF_CHAT, 'booking_id': 1, 'action': 'confirm'}, key='bad').status_code, 401)

    def test_a_counselor_cannot_confirm_an_invitation_waiting_for_the_student(self):
        Booking.objects.filter(pk=self.booking.pk).update(staff_requested=True)
        self.assertEqual(self.action(STAFF_CHAT, 'confirm').status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')

    # --- website side -----------------------------------------------------------------------

    def test_staff_see_student_usernames_and_students_do_not(self):
        self.client.force_authenticate(self.c1)
        row = self.client.get(f'/api/bookings/{self.booking.pk}/').json()
        self.assertEqual((row['student_username'], row['student_telegram_username']), ('stu1', 'sardor_a'))
        self.client.force_authenticate(self.s1.user)
        row = self.client.get(f'/api/bookings/{self.booking.pk}/').json()
        self.assertIsNone(row['student_username'])
        self.assertIsNone(row['student_telegram_username'])

    def test_unlinked_students_show_no_telegram_username(self):
        self.tg.delete()
        self.client.force_authenticate(self.c1)
        self.assertIsNone(self.client.get(f'/api/bookings/{self.booking.pk}/').json()['student_telegram_username'])

    def test_the_bot_meetings_list_carries_the_username(self):
        data = self.post('meetings', {'chat_id': STAFF_CHAT}).json()
        self.assertEqual(data['meetings'][0]['telegram_username'], 'sardor_a')

    def test_a_student_must_have_telegram_to_move_a_meeting(self):
        new = MeetingAvailability.objects.filter(participant=self.c1).exclude(pk=self.slot.pk).first()
        payload = {'starts_at': new.starts_at.isoformat(), 'duration_minutes': 45, 'availability_slot': new.pk}
        self.tg.delete()
        self.client.force_authenticate(self.s1.user)
        refused = self.client.post(f'/api/bookings/{self.booking.pk}/reschedule/', payload, format='json')
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()['code'], 'telegram_required')
        # Cancelling stays possible, and staff are never gated.
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.post(f'/api/bookings/{self.booking.pk}/reschedule/', payload, format='json').status_code, 200)


@override_settings(TELEGRAM_BOT_USERNAME='naseeb_test_bot', FRONTEND_URL='https://app.example.com')
class ResendMeetingCardsTests(MeetingCardTests):
    def run_command(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('resend_meeting_cards', *args, stdout=out)
        return out.getvalue()

    def test_open_meetings_get_one_card_each_with_buttons_and_reruns_send_nothing(self):
        TelegramOutbox.objects.all().delete()
        Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Old', starts_at=timezone.now() - timedelta(days=1),
            duration_minutes=45, status='pending',
        )
        Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Gone', starts_at=soon(5), duration_minutes=45,
            status='cancelled',
        )
        self.assertIn('would send: 1 staff cards, 1 student cards', self.run_command('--dry-run'))
        self.assertFalse(TelegramOutbox.objects.exists())
        self.assertIn('queued: 1 staff cards, 1 student cards', self.run_command())
        staff = TelegramOutbox.objects.get(chat_id=STAFF_CHAT)
        student = TelegramOutbox.objects.get(chat_id=STUDENT_CHAT)
        self.assertIn('@sardor_a', staff.text)
        self.assertIn('mt:confirm:%d' % self.booking.pk, str(staff.buttons))
        self.assertNotIn('mt:', str(student.buttons))
        self.assertIn('queued: 0 staff cards, 0 student cards', self.run_command())

    def test_participant_filter_skips_other_staff(self):
        TelegramOutbox.objects.all().delete()
        self.assertIn('queued: 0 staff cards, 0 student cards', self.run_command('--participant', str(self.c1.pk + 9999)))
