from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from apps.telegram_bot import conf, services
from apps.telegram_bot.digest import TASHKENT, tashkent_now
from apps.telegram_bot.models import TelegramLink

from .base import BotTestCase

DAY = date(2026, 11, 8)


def at(hour, minute, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TASHKENT)


class DueTests(BotTestCase):
    def schedule(self, user, chat, hh_mm='09:00', **extra):
        self.link(user, chat_id=chat)
        hour, minute = map(int, hh_mm.split(':'))
        TelegramLink.objects.filter(chat_id=chat).update(notify_time=time(hour, minute), **extra)
        return chat

    def due_chats(self, now, **kw):
        return sorted(item['chat_id'] for item in services.due(now, **kw))

    def test_due_at_the_exact_tashkent_minute_only(self):
        self.schedule(self.c1, 1)
        self.assertEqual(self.due_chats(at(8, 59)), [])
        self.assertEqual(self.due_chats(at(9, 0)), [1])

    def test_a_utc_clock_is_read_as_tashkent(self):
        self.schedule(self.c1, 1)
        self.assertEqual(self.due_chats(datetime(2026, 11, 8, 4, 0, tzinfo=dt_timezone.utc)), [1])

    @override_settings(TIME_ZONE='UTC')
    def test_utc_configured_process_still_uses_tashkent(self):
        self.assertEqual(tashkent_now().utcoffset(), timedelta(hours=5))
        self.schedule(self.c1, 1, '09:00')
        self.assertEqual(self.due_chats(datetime(2026, 11, 8, 9, 0, tzinfo=dt_timezone.utc)), [])
        self.assertEqual(self.due_chats(datetime(2026, 11, 8, 4, 0, tzinfo=dt_timezone.utc)), [1])

    def test_each_chat_is_returned_once_then_leased(self):
        self.schedule(self.c1, 1)
        self.assertEqual(self.due_chats(at(9, 0)), [1])
        self.assertEqual(self.due_chats(at(9, 0)), [])
        self.assertEqual(self.due_chats(at(9, 1)), [])

    def test_lease_expires_when_the_sender_died(self):
        self.schedule(self.c1, 1)
        self.assertEqual(self.due_chats(at(9, 0)), [1])
        TelegramLink.objects.update(claimed_at=timezone.now() - timedelta(minutes=3))
        self.assertEqual(self.due_chats(at(9, 1)), [1])

    def test_mark_sent_ends_the_day(self):
        self.schedule(self.c1, 1)
        item = services.due(at(9, 0))[0]
        self.assertEqual(item['slot_date'], '2026-11-08')
        self.assertEqual(services.mark_sent(1, DAY), 1)
        TelegramLink.objects.update(claimed_at=None)
        for minute in range(0, 6):
            self.assertEqual(self.due_chats(at(9, minute)), [])
        self.assertEqual(self.due_chats(at(9, 0, date(2026, 11, 9))), [1])

    def test_mark_sent_is_idempotent_and_never_goes_back(self):
        self.schedule(self.c1, 1)
        self.assertEqual(services.mark_sent(1, DAY), 1)
        self.assertEqual(services.mark_sent(1, DAY), 0)
        self.assertEqual(services.mark_sent(1, DAY - timedelta(days=1)), 0)
        self.assertEqual(TelegramLink.objects.get().last_sent_date, DAY)

    def test_catch_up_window(self):
        self.schedule(self.c1, 1)
        self.assertEqual(self.due_chats(at(9, 5)), [1])
        TelegramLink.objects.update(claimed_at=None)
        self.assertEqual(self.due_chats(at(9, 6)), [])
        with mock.patch.object(conf, 'DUE_GRACE_MINUTES', 0):
            self.assertEqual(self.due_chats(at(9, 1)), [])

    def test_around_midnight(self):
        self.schedule(self.c1, 1, '23:58')
        self.schedule(self.c2, 2, '00:00')
        self.assertEqual(self.due_chats(at(23, 58)), [1])
        services.mark_sent(1, DAY)
        TelegramLink.objects.update(claimed_at=None)
        # 00:00 of the next day: the 23:58 chat was already served for Nov 8, the 00:00 chat is due for Nov 9.
        nxt = date(2026, 11, 9)
        items = services.due(at(0, 0, nxt))
        self.assertEqual([(i['chat_id'], i['slot_date']) for i in items], [(2, '2026-11-09')])
        services.mark_sent(2, nxt)
        TelegramLink.objects.update(claimed_at=None)
        self.assertEqual(self.due_chats(at(0, 1, nxt)), [])
        self.assertEqual(self.due_chats(at(23, 58, nxt)), [1])

    def test_catch_up_across_midnight_keeps_the_scheduled_date(self):
        self.schedule(self.c1, 1, '23:58')
        items = services.due(at(0, 2, date(2026, 11, 9)))
        self.assertEqual([(i['chat_id'], i['slot_date']) for i in items], [(1, '2026-11-08')])
        services.mark_sent(1, date(2026, 11, 8))
        TelegramLink.objects.update(claimed_at=None)
        self.assertEqual(self.due_chats(at(0, 3, date(2026, 11, 9))), [])

    def test_unscheduled_paused_and_other_minutes_are_skipped(self):
        self.link(self.c1, chat_id=1)
        self.schedule(self.c2, 2, '09:00', is_active=False)
        self.schedule(self.a1, 3, '10:00')
        self.assertEqual(self.due_chats(at(9, 0)), [])

    def test_batch_is_bounded_and_the_rest_follows_next_minute(self):
        for chat, user in enumerate((self.c1, self.c2, self.cb), start=1):
            self.schedule(user, chat)
        first = self.due_chats(at(9, 0), limit=2)
        self.assertEqual(len(first), 2)
        second = self.due_chats(at(9, 1), limit=2)
        self.assertEqual(sorted(first + second), [1, 2, 3])

    def test_api_endpoint_uses_the_current_tashkent_minute(self):
        self.schedule(self.c1, 1)
        with mock.patch.object(services, 'tashkent_now', return_value=at(9, 0)):
            body = self.post('due').json()
            again = self.post('due').json()
        self.assertEqual(body['chats'], [{'chat_id': 1, 'language': 'uz', 'slot_date': '2026-11-08'}])
        self.assertEqual(again['chats'], [])

    def test_mark_sent_endpoint(self):
        self.schedule(self.c1, 1)
        self.assertTrue(self.post('mark-sent', {'chat_id': 1, 'slot_date': '2026-11-08'}).json()['marked'])
        self.assertFalse(self.post('mark-sent', {'chat_id': 1, 'slot_date': '2026-11-08'}).json()['marked'])
        self.assertEqual(self.post('mark-sent', {'chat_id': 1, 'slot_date': 'x'}).status_code, 400)
