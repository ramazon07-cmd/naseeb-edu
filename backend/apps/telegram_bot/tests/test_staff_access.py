from rest_framework.test import APIClient

from apps.telegram_bot.models import PendingLogin, StaffTelegramAccess, TelegramLink
from apps.users.models import User

from .base import PASSWORD, BotTestCase, make_user, tg_name

URL = '/api/telegram/staff-access/'


class StaffAccessApiTests(BotTestCase):
    def setUp(self):
        super().setUp()
        StaffTelegramAccess.objects.all().delete()
        self.admin = make_user('admin1', User.Role.ADMIN)
        self.web = APIClient()
        self.web.force_authenticate(self.admin)

    def put(self, user, value, client=None):
        return (client or self.web).put(f'{URL}{user.pk}/', {'telegram_username': value}, format='json')

    def test_only_admins_may_read_or_change_it(self):
        for who in (self.c1, self.a1, self.s1.user, make_user('teacher1', User.Role.TEACHER, self.school_a)):
            client = APIClient()
            client.force_authenticate(who)
            self.assertEqual(client.get(URL).status_code, 403, who.role)
            self.assertEqual(client.get(f'{URL}{self.c1.pk}/').status_code, 403)
            self.assertEqual(self.put(self.c1, 'someone_1', client).status_code, 403)
            self.assertEqual(client.delete(f'{URL}{self.c1.pk}/').status_code, 403)
        anonymous = APIClient()
        self.assertEqual(anonymous.get(URL).status_code, 401)
        self.assertFalse(StaffTelegramAccess.objects.exists())

    def test_lower_admin_tiers_are_refused(self):
        for tier in (User.AdminTier.SUPPORT, User.AdminTier.OPS):
            lower = make_user(f'admin_{tier}', User.Role.ADMIN, admin_tier=tier)
            client = APIClient()
            client.force_authenticate(lower)
            self.assertEqual(client.get(URL).status_code, 403, tier)
            self.assertEqual(self.put(self.c1, 'someone_1', client).status_code, 403, tier)
        self.assertFalse(StaffTelegramAccess.objects.exists())

    def test_superuser_without_admin_role_may_manage_it(self):
        boss = make_user('boss', User.Role.COUNSELOR, self.school_a, is_superuser=True)
        client = APIClient()
        client.force_authenticate(boss)
        self.assertEqual(self.put(self.c1, 'someone_1', client).status_code, 200)

    def test_set_normalizes_and_lists(self):
        response = self.put(self.c1, '  @Dilnoza_K  ')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['telegram_username'], 'dilnoza_k')
        access = StaffTelegramAccess.objects.get()
        self.assertEqual((access.user, access.created_by, access.telegram_username), (self.c1, self.admin, 'dilnoza_k'))
        self.assertEqual(self.put(self.a1, 'assist_ant').status_code, 200)
        listed = self.web.get(URL).json()['results']
        self.assertEqual([(r['user_id'], r['telegram_username'], r['role']) for r in listed], [
            (self.a1.pk, 'assist_ant', 'assistant'), (self.c1.pk, 'dilnoza_k', 'counselor'),
        ])
        self.assertEqual(self.web.get(f'{URL}{self.c1.pk}/').json()['telegram_username'], 'dilnoza_k')
        self.assertEqual(self.web.get(f'{URL}{self.c2.pk}/').json()['telegram_username'], '')

    def test_changing_keeps_one_row_and_the_original_creator(self):
        self.put(self.c1, 'first_name')
        other = make_user('admin2', User.Role.ADMIN)
        client = APIClient()
        client.force_authenticate(other)
        self.put(self.c1, 'second_name', client)
        access = StaffTelegramAccess.objects.get()
        self.assertEqual((access.telegram_username, access.created_by), ('second_name', self.admin))

    def test_validation(self):
        for bad in ('', '   ', '@', 'abcd', 'a' * 33, 'has space', 'dash-name', 'юзернейм', 'name!', None, 123456, 'a.b.c.d'):
            response = self.put(self.c1, bad)
            self.assertEqual((response.status_code, response.json()['code']), (400, 'invalid_username'), repr(bad))
        self.assertEqual(self.put(self.c1, 'a' * 32).status_code, 200)
        self.assertEqual(self.put(self.c2, 'Ab_12').status_code, 200)

    def test_username_is_unique_case_insensitively(self):
        self.put(self.c1, 'shared_one')
        response = self.put(self.c2, '@SHARED_ONE')
        self.assertEqual((response.status_code, response.json()['code']), (409, 'username_taken'))
        self.assertEqual(StaffTelegramAccess.objects.count(), 1)
        # Re-saving the same value for the same user is fine.
        self.assertEqual(self.put(self.c1, 'Shared_One').status_code, 200)

    def test_only_counselors_and_assistants(self):
        for user in (self.s1.user, self.admin, make_user('parent1', User.Role.PARENT)):
            response = self.put(user, 'student_one')
            self.assertEqual((response.status_code, response.json()['code']), (400, 'role_not_allowed'), user.role)
        self.assertEqual(self.put(User(pk=999999), 'student_one').json()['code'], 'not_found')
        self.assertFalse(StaffTelegramAccess.objects.exists())

    def test_clear(self):
        self.put(self.c1, 'dilnoza_k')
        self.assertEqual(self.web.delete(f'{URL}{self.c1.pk}/').status_code, 204)
        self.assertFalse(StaffTelegramAccess.objects.exists())
        self.assertEqual(self.web.delete(f'{URL}{self.c1.pk}/').status_code, 204)

    def test_deleting_the_user_removes_the_entry(self):
        self.put(self.c2, 'dilnoza_k')
        self.c2.delete()
        self.assertFalse(StaffTelegramAccess.objects.exists())


class AllowlistLoginTests(BotTestCase):
    def login(self, username, tg, chat=None, password=PASSWORD):
        data = {'chat_id': chat or self.chat, 'username': username, 'password': password}
        if tg is not None:
            data['telegram_username'] = tg
        return self.post('login', data)

    def test_the_assigned_telegram_user_can_log_in_case_insensitively_and_with_at(self):
        for tg in (tg_name('counselor1'), tg_name('counselor1').upper(), '@' + tg_name('counselor1')):
            self.assertEqual(self.login('counselor1', tg).status_code, 200, tg)

    def test_missing_unknown_or_empty_username_is_refused_before_the_password(self):
        for tg in ('', '  ', '@', 'not_on_the_list'):
            response = self.login('counselor1', tg, password='wrong-password-1')
            self.assertEqual((response.status_code, response.json()['code']), (403, 'telegram_not_allowed'), repr(tg))
        self.assertFalse(PendingLogin.objects.exists())

    def test_a_login_without_any_telegram_username_is_refused(self):
        self.client.force_authenticate(None)
        response = self.client.post(
            '/api/bot/login/', {'chat_id': 1, 'username': 'counselor1', 'password': PASSWORD}, format='json',
            HTTP_X_BOT_SERVICE_KEY='test-service-key-0123456789abcdef',
        )
        self.assertEqual((response.status_code, response.json()['code']), (403, 'telegram_not_allowed'))

    def test_refused_chats_do_not_burn_password_attempts(self):
        for _ in range(8):
            self.login('counselor1', 'not_on_the_list', password='wrong-password-1')
        self.assertEqual(self.login('counselor1', tg_name('counselor1')).status_code, 200)

    def test_an_allowed_user_cannot_log_in_to_someone_elses_account(self):
        response = self.login('counselor2', tg_name('counselor1'))
        self.assertEqual((response.status_code, response.json()['code']), (403, 'telegram_not_allowed'))
        self.assertFalse(PendingLogin.objects.exists())
        self.assertEqual(self.login('counselor2', tg_name('counselor2')).status_code, 200)

    def test_an_account_without_an_entry_cannot_log_in_even_from_an_allowed_username(self):
        StaffTelegramAccess.objects.filter(user=self.c2).delete()
        self.assertEqual(self.login('counselor2', tg_name('counselor1')).json()['code'], 'telegram_not_allowed')

    def test_removing_the_entry_blocks_new_logins_but_keeps_an_existing_link(self):
        chat = self.link(self.c1)
        StaffTelegramAccess.objects.filter(user=self.c1).delete()
        self.assertEqual(self.login('counselor1', tg_name('counselor1'), chat=chat + 1).json()['code'], 'telegram_not_allowed')
        self.assertEqual(self.post('students', {'chat_id': chat}).status_code, 200)
        self.assertEqual(TelegramLink.objects.count(), 1)

    def test_whoami_kinds(self):
        def who(chat, tg=None):
            data = {'chat_id': chat}
            if tg is not None:
                data['telegram_username'] = tg
            body = self.post('whoami', data).json()
            self.assertTrue(body.pop('site_url').endswith('/meetings'))
            return body

        self.assertEqual(who(5000), {'kind': 'unknown'})
        self.assertEqual(who(5000, 'nobody_here'), {'kind': 'unknown'})
        self.assertEqual(who(5000, '@' + tg_name('counselor1').upper()), {'kind': 'staff_allowed'})
        chat = self.link(self.c1)
        # A linked chat is a linked counselor, with or without a username on the list.
        StaffTelegramAccess.objects.filter(user=self.c1).delete()
        self.assertEqual(who(chat), {'kind': 'staff_linked', 'name': 'Counselor1 Tester'})
        # A student's chat.
        from apps.telegram_bot.models import StudentTelegram
        StudentTelegram.objects.create(user=self.s1.user, chat_id=7000)
        self.assertEqual(who(7000, 'anyone_x'), {'kind': 'student', 'name': 'Stu1 Tester'})
        StudentTelegram.objects.update(is_active=False)
        self.assertEqual(who(7000), {'kind': 'unknown'})

    def test_whoami_ignores_a_dead_link_and_deactivated_staff(self):
        chat = self.link(self.c1)
        User.objects.filter(pk=self.c1.pk).update(is_active=False)
        self.assertEqual(self.post('whoami', {'chat_id': chat}).json()['kind'], 'unknown')
        self.assertFalse(TelegramLink.objects.exists())
        listed = self.post('whoami', {'chat_id': 1, 'telegram_username': tg_name('counselor1')}).json()
        self.assertEqual(listed['kind'], 'unknown')

    def test_whoami_needs_the_key_and_valid_input(self):
        self.assertEqual(self.post('whoami', {'chat_id': 1}, key=None).status_code, 401)
        self.assertEqual(self.post('whoami', {'chat_id': 'x'}).status_code, 400)
        self.assertEqual(self.post('whoami', {'chat_id': 1, 'telegram_username': 5}).status_code, 400)
        self.assertEqual(self.post('login', {'chat_id': 1, 'username': 'a', 'password': 'b', 'telegram_username': 5}).status_code, 400)
