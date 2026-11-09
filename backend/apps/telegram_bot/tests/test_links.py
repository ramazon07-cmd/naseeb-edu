from datetime import datetime, timedelta

from apps.admissions.models import School
from apps.telegram_bot.models import TelegramLink
from apps.users.models import User

from .base import PASSWORD, BotTestCase


class LinkValidityTests(BotTestCase):
    def assert_link_dead(self, chat):
        for method, path, data in (
            ('post', 'students', {'chat_id': chat}), ('post', 'digest', {'chat_id': chat}),
            ('get', 'settings', {'chat_id': chat}), ('put', 'settings', {'chat_id': chat, 'language': 'en'}),
        ):
            response = self.call(method, path, data)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json()['code'], 'not_linked')
        self.assertFalse(TelegramLink.objects.filter(chat_id=chat).exists())

    def test_deactivated_user(self):
        chat = self.link(self.c1)
        User.objects.filter(pk=self.c1.pk).update(is_active=False)
        self.assert_link_dead(chat)

    def test_changed_password(self):
        chat = self.link(self.c1)
        self.assertEqual(self.post('students', {'chat_id': chat}).status_code, 200)
        self.c1.set_password('AnotherPass456!')
        self.c1.password_version += 1
        self.c1.save()
        self.assert_link_dead(chat)

    def test_a_hasher_upgrade_on_a_website_login_keeps_the_link(self):
        chat = self.link(self.c1)
        self.c1.set_password(PASSWORD)
        self.c1.save()
        self.assertEqual(self.post('students', {'chat_id': chat}).status_code, 200)

    def test_a_forced_password_change_kills_the_link(self):
        chat = self.link(self.c1)
        User.objects.filter(pk=self.c1.pk).update(must_change_password=True)
        self.assert_link_dead(chat)

    def test_confirm_is_refused_once_a_password_change_is_forced(self):
        login = self.post('login', {'chat_id': self.chat, 'username': 'counselor1', 'password': PASSWORD})
        User.objects.filter(pk=self.c1.pk).update(must_change_password=True)
        response = self.post('confirm', {'chat_id': self.chat, 'pending_token': login.json()['pending_token']})
        self.assertEqual(response.status_code, 410)
        self.assertFalse(TelegramLink.objects.exists())

    def test_role_change(self):
        for role in (User.Role.TEACHER, User.Role.ORGANIZATION, User.Role.ADMIN):
            chat = self.link(self.c1)
            User.objects.filter(pk=self.c1.pk).update(role=role)
            self.assert_link_dead(chat)
            User.objects.filter(pk=self.c1.pk).update(role=User.Role.COUNSELOR)

    def test_assistant_role_change(self):
        chat = self.link(self.a1)
        User.objects.filter(pk=self.a1.pk).update(role=User.Role.TEACHER)
        self.assert_link_dead(chat)

    def test_deactivated_assistant(self):
        chat = self.link(self.a1)
        User.objects.filter(pk=self.a1.pk).update(is_active=False)
        self.assert_link_dead(chat)

    def test_assistant_loses_counselor(self):
        chat = self.link(self.a1)
        User.objects.filter(pk=self.a1.pk).update(supervising_counselor=None)
        self.assert_link_dead(chat)

    def test_assistant_whose_counselor_is_deactivated_or_demoted(self):
        chat = self.link(self.a1)
        User.objects.filter(pk=self.c1.pk).update(is_active=False)
        self.assert_link_dead(chat)
        User.objects.filter(pk=self.c1.pk).update(is_active=True, role=User.Role.TEACHER)
        self.assertEqual(self.post('login', {'chat_id': chat, 'username': 'assistant1', 'password': 'StrongPass123!'}).status_code, 403)

    def test_school_deactivated(self):
        chat = self.link(self.c1)
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)
        self.assert_link_dead(chat)

    def test_other_links_are_untouched(self):
        mine, other = self.link(self.c1, 1), self.link(self.c2, 2)
        User.objects.filter(pk=self.c1.pk).update(is_active=False)
        self.assert_link_dead(mine)
        self.assertEqual(self.post('students', {'chat_id': other}).status_code, 200)


class SettingsTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.chat = self.link(self.c1)

    def put(self, **data):
        return self.call('put', 'settings', {'chat_id': self.chat, **data})

    def test_defaults(self):
        body = self.call('get', 'settings', {'chat_id': self.chat}).json()
        self.assertEqual(body['prefs'], {'essays': True, 'streak': True, 'application': True})
        self.assertIsNone(body['notify_time'])
        self.assertEqual(body['language'], 'uz')

    def test_update_time_language_and_toggles(self):
        body = self.put(notify_time='21:00', language='en', prefs={'streak': False}).json()
        self.assertEqual(body['notify_time'], '21:00')
        self.assertEqual(body['language'], 'en')
        self.assertEqual(body['prefs'], {'essays': True, 'streak': False, 'application': True})
        self.assertEqual(self.call('get', 'settings', {'chat_id': self.chat}).json(), body)

    def test_invalid_values(self):
        for data in ({'notify_time': '25:00'}, {'notify_time': 'abc'}, {'language': 'de'}, {'prefs': {'x': True}},
                     {'prefs': {'essays': 'yes'}}, {'prefs': []}, {'enabled': 'no'}):
            self.assertEqual(self.put(**data).status_code, 400, data)

    def test_setting_a_time_that_passed_today_does_not_send_instantly(self):
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 8, 12, 0, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        from apps.telegram_bot import services
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 9, 0).time(), now=now)
        self.assertEqual(str(link.last_sent_date), '2026-11-08')
        link.last_sent_date = None
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 18, 0).time(), now=now)
        self.assertIsNone(link.last_sent_date)

    def test_a_time_that_just_passed_still_sends_today_inside_the_grace_window(self):
        from apps.telegram_bot import services
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 8, 12, 0, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 11, 58).time(), now=now)
        self.assertIsNone(link.last_sent_date)
        self.assertEqual([item['chat_id'] for item in services.due(now)], [self.chat])

    def test_a_time_just_before_midnight_set_just_after_it_does_not_send_twice(self):
        from apps.telegram_bot import services
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 9, 0, 2, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 23, 59).time(), now=now)
        self.assertEqual(str(link.last_sent_date), '2026-11-08')
        self.assertEqual(services.due(now), [])
        self.assertEqual([i['chat_id'] for i in services.due(datetime(2026, 11, 9, 23, 59, tzinfo=TASHKENT))], [self.chat])

    def test_a_yesterday_slot_is_not_due_when_the_update_already_went_out_today(self):
        from apps.telegram_bot import services
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 9, 0, 2, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        link.last_sent_date = now.date()
        link.save(update_fields=['last_sent_date'])
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 23, 58).time(), now=now)
        self.assertEqual(services.due(now), [])

    def test_a_null_notify_time_clears_it_and_nothing_is_due(self):
        from apps.telegram_bot import services
        from apps.telegram_bot.digest import TASHKENT

        self.put(notify_time='12:00')
        body = self.put(notify_time=None).json()
        self.assertIsNone(body['notify_time'])
        self.assertIsNone(TelegramLink.objects.get().notify_time)
        self.assertEqual(services.due(datetime(2026, 11, 8, 12, 0, tzinfo=TASHKENT)), [])

    def test_an_omitted_notify_time_is_left_alone(self):
        self.put(notify_time='12:00')
        self.assertEqual(self.put(language='en').json()['notify_time'], '12:00')

    def test_a_non_string_language_is_a_400(self):
        for value in (['uz'], {}, 5, True):
            self.assertEqual(self.put(language=value).status_code, 400, value)
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': 'x', 'language': ['uz']}).status_code, 400)

    def test_moving_the_time_later_after_todays_send_applies_from_tomorrow(self):
        from apps.telegram_bot import services
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 8, 10, 0, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        link.last_sent_date = now.date()
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 18, 0).time(), now=now)
        self.assertEqual(link.last_sent_date, now.date())
        link.last_sent_date = now.date() - timedelta(days=1)
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 19, 0).time(), now=now)
        self.assertEqual(link.last_sent_date, now.date() - timedelta(days=1))

    def test_digest_only_has_the_enabled_parts(self):
        self.put(prefs={'essays': False, 'streak': False, 'application': True})
        student = self.post('digest', {'chat_id': self.chat}).json()['students'][0]
        self.assertEqual(set(student), {'name', 'grade', 'application'})
        self.put(prefs={'essays': True, 'streak': True, 'application': False})
        student = self.post('digest', {'chat_id': self.chat}).json()['students'][0]
        self.assertEqual(set(student), {'name', 'grade', 'essays', 'streak'})
