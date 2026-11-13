from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import School
from apps.telegram_bot.models import PendingLogin, TelegramLink
from apps.users.models import User

from .base import KEY, PASSWORD, BotTestCase, make_user

ENDPOINTS = [
    ('post', 'login'), ('post', 'confirm'), ('post', 'students'), ('post', 'digest'), ('get', 'settings'),
    ('put', 'settings'), ('post', 'due'), ('post', 'mark-sent'), ('post', 'logout'), ('post', 'unlink'),
]


class ServiceKeyTests(BotTestCase):
    def test_every_endpoint_needs_the_key(self):
        for method, path in ENDPOINTS:
            for key in (None, '', 'wrong', KEY + 'x', KEY[:-1]):
                response = self.call(method, path, {'chat_id': 1}, key=key)
                self.assertEqual(response.status_code, 401, (method, path, key))
                self.assertNotIn('code', response.json())

    @override_settings(BOT_SERVICE_KEY='')
    def test_unset_key_disables_the_api_even_for_an_empty_header(self):
        for key in (None, '', 'anything'):
            self.assertEqual(self.post('due', key=key).status_code, 401)

    def test_login_cannot_reach_the_api_without_key_even_with_valid_credentials(self):
        response = self.post('login', {'chat_id': 1, 'username': 'counselor1', 'password': PASSWORD}, key=None)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(PendingLogin.objects.exists())


class LoginTests(BotTestCase):
    def login(self, username, password=PASSWORD, chat=None):
        return self.post('login', {'chat_id': chat or self.chat, 'username': username, 'password': password})

    def test_counselor_login_confirm_students(self):
        response = self.login('counselor1')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['full_name'], 'Counselor1 Tester')
        self.assertEqual(body['email'], 'counselor1@example.com')
        self.assertEqual(body['phone'], '+998901112233')
        self.assertNotIn(PASSWORD, response.content.decode())
        self.assertFalse(TelegramLink.objects.exists())

        confirm = self.post('confirm', {'chat_id': self.chat, 'pending_token': body['pending_token'], 'language': 'ru'})
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()['language'], 'ru')
        self.assertIsNone(confirm.json()['notify_time'])
        self.assertEqual(TelegramLink.objects.get().user, self.c1)
        self.assertFalse(PendingLogin.objects.exists())

        students = self.post('students', {'chat_id': self.chat})
        self.assertEqual(students.status_code, 200)
        self.assertEqual(students.json()['total'], 2)
        self.assertEqual([(g['grade'], g['count']) for g in students.json()['groups']], [('9', 1), ('10', 1)])

    def test_login_by_email(self):
        self.assertEqual(self.login('Counselor1@Example.com').status_code, 200)

    def test_nothing_in_the_database_holds_the_password(self):
        self.login('counselor1')
        pending = PendingLogin.objects.get()
        self.assertNotIn(PASSWORD, f'{pending.token_hash}{pending.auth_fingerprint}')

    def test_chat_id_beyond_bigint_is_a_400_not_a_500(self):
        huge = 2 ** 70
        self.assertEqual(self.post('login', {'chat_id': huge, 'username': 'x', 'password': 'y'}).status_code, 400)
        self.assertEqual(self.post('students', {'chat_id': huge}).status_code, 400)
        self.assertEqual(self.call('get', 'settings', {'chat_id': huge}).status_code, 400)

    def test_wrong_password_and_unknown_user_look_the_same(self):
        wrong = self.login('counselor1', 'bad-password-1')
        unknown = self.login('nobody-here', 'bad-password-1')
        self.assertEqual(wrong.status_code, unknown.status_code)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(wrong.status_code, 401)

    def test_inactive_account_looks_like_a_wrong_password(self):
        User.objects.filter(pk=self.c1.pk).update(is_active=False)
        self.assertEqual(self.login('counselor1').json(), self.login('nobody-here').json())

    def test_non_counselor_roles_are_refused_and_nothing_is_stored(self):
        teacher = make_user('teacher1', User.Role.TEACHER, self.school_a)
        org = make_user('org1', User.Role.ORGANIZATION, self.school_a)
        parent = make_user('parent1', User.Role.PARENT)
        admin = make_user('admin1', User.Role.ADMIN)
        for user in (self.s1.user, self.s4.user, teacher, org, parent, admin):
            response = self.login(user.username)
            self.assertEqual(response.status_code, 403, user.role)
            self.assertEqual(response.json()['code'], 'role_not_allowed')
        self.assertFalse(PendingLogin.objects.exists())
        self.assertFalse(TelegramLink.objects.exists())

    def test_superuser_with_counselor_role_is_refused(self):
        boss = make_user('boss', User.Role.COUNSELOR, self.school_a, is_superuser=True)
        self.assertEqual(self.login(boss.username).status_code, 403)

    def test_temporary_password_must_be_changed_on_the_site_first(self):
        User.objects.filter(pk=self.c1.pk).update(must_change_password=True)
        self.assertEqual(self.login('counselor1').json()['code'], 'password_change_required')
        self.assertFalse(PendingLogin.objects.exists())

    def test_deactivated_school_is_refused(self):
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)
        self.assertEqual(self.login('counselor1').status_code, 403)

    def test_assistant_without_counselor_is_refused(self):
        User.objects.filter(pk=self.a1.pk).update(supervising_counselor=None)
        self.assertEqual(self.login('assistant1').status_code, 403)

    def test_lockout_per_chat_after_five_failures(self):
        for _ in range(5):
            self.assertEqual(self.login('counselor1', 'bad-password-1').status_code, 401)
        locked = self.login('counselor1', PASSWORD)
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()['code'], 'locked')
        self.assertFalse(PendingLogin.objects.exists())

    def test_another_chat_cannot_lock_the_owner_out(self):
        for chat in range(20):
            self.login('counselor1', 'bad-password-1', chat=2000 + (chat % 2))
        self.assertEqual(self.login('counselor1', PASSWORD, chat=3000).status_code, 200)

    def test_lockout_per_chat_across_usernames_and_unknown_users_count_too(self):
        for i in range(5):
            self.login(f'ghost{i}', 'bad-password-1')
        self.assertEqual(self.login('counselor1', PASSWORD).status_code, 429)

    @override_settings()
    def test_many_chats_guessing_one_account_hit_the_ceiling_but_a_known_chat_does_not(self):
        from apps.telegram_bot import conf
        known = self.login('counselor1', PASSWORD, chat=6000)
        self.assertEqual(known.status_code, 200)
        for chat in range(conf.ACCOUNT_CEILING):
            self.login('counselor1', 'bad-password-1', chat=7000 + chat)
        stranger = self.login('counselor1', PASSWORD, chat=9999)
        self.assertEqual(stranger.status_code, 429)
        self.assertEqual(stranger.json()['code'], 'locked')
        self.assertEqual(self.login('counselor1', PASSWORD, chat=6000).status_code, 200)

    def test_username_and_email_in_one_chat_share_the_chat_counter(self):
        for i in range(5):
            who = 'counselor1' if i % 2 else 'counselor1@example.com'
            self.assertEqual(self.login(who, 'bad-password-1', chat=4000).status_code, 401)
        self.assertEqual(self.login('counselor1', PASSWORD, chat=4000).status_code, 429)
        self.assertEqual(self.login('Counselor1@Example.com', PASSWORD, chat=4000).status_code, 429)

    def test_expired_pending_logins_are_purged_on_the_next_login(self):
        self.login('counselor1', chat=8100)
        PendingLogin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.login('counselor2', chat=8101)
        self.assertEqual(list(PendingLogin.objects.values_list('chat_id', flat=True)), [8101])

    def test_a_username_containing_an_at_sign_still_logs_in(self):
        User.objects.filter(pk=self.c2.pk).update(username='odd@name', email='other@example.com')
        user = User.objects.get(pk=self.c2.pk)
        user.set_password(PASSWORD)
        user.save()
        self.assertEqual(self.login('odd@name', PASSWORD, chat=8000).status_code, 200)

    def test_an_email_shared_by_two_accounts_is_refused(self):
        User.objects.filter(pk=self.c2.pk).update(email=self.c1.email.upper())
        response = self.login(self.c1.email)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'invalid_credentials')
        self.assertEqual(self.login('counselor1').status_code, 200)

    def test_bot_failures_use_the_website_counter_without_locking_web_addresses(self):
        from apps.users.cache_safety import cache_get
        from apps.users.security import _key, login_locked
        for _ in range(3):
            self.login('counselor1', 'bad-password-1', chat=4000)
        self.assertEqual(cache_get(_key('user-ip', 'counselor1|telegram:4000')), 3)
        self.assertIsNone(cache_get(_key('user-ip', 'counselor1|telegram')))
        self.assertFalse(login_locked(('user-ip', 'counselor1|203.0.113.7')))

    def test_website_threshold_blocks_the_same_chat_even_with_a_fresh_bot_counter(self):
        from apps.users.security import register_login_failure
        for _ in range(10):
            register_login_failure(('user-ip', 'counselor1|telegram:5000'))
        self.assertEqual(self.login('counselor1', PASSWORD, chat=5000).status_code, 429)

    def test_lockout_message_is_the_same_for_unknown_users(self):
        for _ in range(5):
            self.login('ghost', 'bad-password-1')
        self.assertEqual(self.login('ghost', 'x').json()['code'], 'locked')

    def test_success_resets_the_counter(self):
        for _ in range(4):
            self.login('counselor1', 'bad-password-1')
        self.assertEqual(self.login('counselor1').status_code, 200)
        for _ in range(4):
            self.login('counselor1', 'bad-password-1')
        self.assertEqual(self.login('counselor1').status_code, 200)

    def test_bad_payloads_are_400(self):
        for data in ({}, {'chat_id': 'x', 'username': 'a', 'password': 'b'}, {'chat_id': 1, 'username': 'a'},
                     {'chat_id': 1, 'username': '', 'password': 'b'}, {'chat_id': True, 'username': 'a', 'password': 'b'}):
            self.assertEqual(self.post('login', data).status_code, 400, data)

    def test_confirm_needs_the_token_of_the_same_chat(self):
        token = self.login('counselor1').json()['pending_token']
        self.assertEqual(self.post('confirm', {'chat_id': 4242, 'pending_token': token}).status_code, 410)
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': 'nope'}).status_code, 410)
        self.assertFalse(TelegramLink.objects.exists())

    def test_confirm_token_is_single_use_and_expires(self):
        token = self.login('counselor1').json()['pending_token']
        PendingLogin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': token}).status_code, 410)
        token = self.login('counselor1').json()['pending_token']
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': token}).status_code, 200)
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': token}).status_code, 410)

    def test_password_change_between_login_and_confirm_voids_the_token(self):
        token = self.login('counselor1').json()['pending_token']
        self.c1.set_password('AnotherPass456!')
        self.c1.password_version += 1
        self.c1.save()
        self.assertEqual(self.post('confirm', {'chat_id': self.chat, 'pending_token': token}).status_code, 410)

    def test_new_login_from_the_same_chat_replaces_the_link(self):
        self.link(self.c1)
        self.link(self.c2)
        self.assertEqual(list(TelegramLink.objects.values_list('user', flat=True)), [self.c2.pk])
        self.assertEqual(self.names(self.post('students', {'chat_id': self.chat})), ['Stu3 Tester'])

    def test_one_account_is_linked_to_one_chat_newest_wins(self):
        self.link(self.c1, chat_id=1)
        self.link(self.c1, chat_id=2)
        self.assertEqual(list(TelegramLink.objects.values_list('chat_id', flat=True)), [2])
        self.assertEqual(self.post('students', {'chat_id': 1}).status_code, 404)
        self.assertEqual(self.post('students', {'chat_id': 2}).status_code, 200)

    def test_logout_wipes_everything(self):
        self.link(self.c1)
        self.post('login', {'chat_id': self.chat, 'username': 'counselor2', 'password': PASSWORD})
        self.assertEqual(self.post('logout', {'chat_id': self.chat}).status_code, 200)
        self.assertFalse(TelegramLink.objects.exists())
        self.assertFalse(PendingLogin.objects.exists())
        self.assertEqual(self.post('students', {'chat_id': self.chat}).json()['code'], 'not_linked')

    def test_unlink_on_block_is_idempotent(self):
        self.link(self.c1)
        self.assertEqual(self.post('unlink', {'chat_id': self.chat}).status_code, 200)
        self.assertEqual(self.post('unlink', {'chat_id': self.chat}).status_code, 200)
        self.assertFalse(TelegramLink.objects.exists())
