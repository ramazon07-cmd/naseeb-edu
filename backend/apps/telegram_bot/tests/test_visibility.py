from apps.admissions.models import StudentProfile
from apps.telegram_bot.models import TelegramLink
from apps.users.models import User

from .base import BotTestCase, make_student, make_user

NAMES = {name: f'{name.title()} Tester' for name in ('stu1', 'stu2', 'stu3', 'stu4', 'stu5')}


class VisibilityMatrixTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.c_empty = make_user('counselor-empty', User.Role.COUNSELOR, self.school_a)
        self.a_empty = make_user('assistant-empty', User.Role.ASSISTANT, self.school_a, supervising_counselor=self.c1)
        self.chats = {}
        for index, user in enumerate((self.c1, self.a1, self.c2, self.a2, self.cb, self.c_empty, self.a_empty)):
            self.chats[user.username] = self.link(user, chat_id=100 + index)

    def seen(self, username, path='students'):
        response = self.post(path, {'chat_id': self.chats[username]})
        self.assertEqual(response.status_code, 200)
        if path == 'students':
            return {name for name in self.names(response)}
        return {item['name'] for item in response.json()['students']}

    def expect(self, **expected):
        for path in ('students', 'digest'):
            for username, stus in expected.items():
                username = username.replace('_', '-')
                self.assertEqual(self.seen(username, path), {NAMES[s] for s in stus}, (username, path))

    def test_matrix(self):
        self.expect(
            counselor1=['stu1', 'stu2'], assistant1=['stu2'],
            counselor2=['stu3'], assistant2=['stu3'],
            counselorb=['stu4'], counselor_empty=[], assistant_empty=[],
        )

    def test_counselor_sees_students_given_to_an_assistant_and_assistant_only_those(self):
        self.assertEqual(self.seen('counselor1'), {NAMES['stu1'], NAMES['stu2']})
        self.assertEqual(self.seen('assistant1'), {NAMES['stu2']})

    def test_student_of_another_school_assigned_to_counselor_is_not_shown(self):
        make_student('stu5', self.school_b, self.c1)
        self.assertNotIn(NAMES['stu5'], self.seen('counselor1'))
        self.assertNotIn(NAMES['stu5'], self.seen('counselor1', 'digest'))

    def test_no_students_is_a_normal_empty_answer(self):
        for path in ('students', 'digest'):
            response = self.post(path, {'chat_id': self.chats['counselor-empty']})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post('students', {'chat_id': self.chats['counselor-empty']}).json(), {'total': 0, 'groups': []})
        digest = self.post('digest', {'chat_id': self.chats['counselor-empty']}).json()
        self.assertEqual((digest['total_students'], digest['students']), (0, []))

    def test_moving_a_student_to_another_counselor_applies_on_the_next_call(self):
        StudentProfile.objects.filter(pk=self.s1.pk).update(assigned_counselor=self.c2)
        self.expect(counselor1=['stu2'], counselor2=['stu1', 'stu3'], assistant1=['stu2'])

    def test_giving_a_student_to_an_assistant_and_taking_them_back(self):
        StudentProfile.objects.filter(pk=self.s1.pk).update(assigned_assistant=self.a1)
        self.expect(counselor1=['stu1', 'stu2'], assistant1=['stu1', 'stu2'])
        StudentProfile.objects.filter(pk=self.s2.pk).update(assigned_assistant=None)
        self.expect(counselor1=['stu1', 'stu2'], assistant1=['stu1'])

    def test_student_moved_away_from_the_assistants_counselor_drops_out_for_the_assistant(self):
        StudentProfile.objects.filter(pk=self.s2.pk).update(assigned_counselor=self.c2)
        self.expect(assistant1=[], counselor1=['stu1'], counselor2=['stu2', 'stu3'])

    def test_deactivated_student_is_not_listed(self):
        User.objects.filter(pk=self.s1.user_id).update(is_active=False)
        self.expect(counselor1=['stu2'])

    def test_crafted_ids_cannot_widen_the_scope(self):
        chat = self.chats['counselor1']
        for path in ('digest', 'students'):
            response = self.post(path, {
                'chat_id': chat, 'student_id': self.s4.pk, 'student_ids': [self.s3.pk, self.s4.pk],
                'user_id': self.cb.pk, 'counselor_id': self.cb.pk,
            })
            text = response.content.decode()
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(NAMES['stu4'], text)
            self.assertNotIn(NAMES['stu3'], text)
        for crafted in (7, -1, 0, 99999999999):
            self.assertEqual(self.post('digest', {'chat_id': crafted}).status_code, 404)

    def test_another_counselors_students_never_appear_in_any_response(self):
        for username in ('counselor1', 'assistant1'):
            for path in ('students', 'digest'):
                body = self.post(path, {'chat_id': self.chats[username]}).content.decode()
                for name in ('stu3', 'stu4'):
                    self.assertNotIn(NAMES[name], body)

    def test_settings_response_has_no_student_data(self):
        body = self.call('get', 'settings', {'chat_id': self.chats['counselor1']}).content.decode()
        self.assertNotIn('Stu', body)

    def test_links_are_separate_per_account(self):
        self.assertEqual(TelegramLink.objects.count(), 7)
