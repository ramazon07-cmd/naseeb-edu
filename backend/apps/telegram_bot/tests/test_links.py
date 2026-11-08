from apps.admissions.models import School
from apps.telegram_bot.models import TelegramLink
from apps.users.models import User

from .base import BotTestCase


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
        self.c1.save()
        self.assert_link_dead(chat)

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
        from datetime import datetime
        from apps.telegram_bot.digest import TASHKENT

        now = datetime(2026, 11, 8, 12, 0, tzinfo=TASHKENT)
        link = TelegramLink.objects.get()
        from apps.telegram_bot import services
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 9, 0).time(), now=now)
        self.assertEqual(str(link.last_sent_date), '2026-11-08')
        link.last_sent_date = None
        services.update_settings(link, notify_time=datetime(2026, 1, 1, 18, 0).time(), now=now)
        self.assertIsNone(link.last_sent_date)

    def test_digest_only_has_the_enabled_parts(self):
        self.put(prefs={'essays': False, 'streak': False, 'application': True})
        student = self.post('digest', {'chat_id': self.chat}).json()['students'][0]
        self.assertEqual(set(student), {'name', 'grade', 'application'})
        self.put(prefs={'essays': True, 'streak': True, 'application': False})
        student = self.post('digest', {'chat_id': self.chat}).json()['students'][0]
        self.assertEqual(set(student), {'name', 'grade', 'essays', 'streak'})
