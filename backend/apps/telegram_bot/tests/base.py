from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.models import User

KEY = 'test-service-key-0123456789abcdef'
PASSWORD = 'StrongPass123!'


def make_user(username, role, school=None, **extra):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password=PASSWORD, role=role, school=school,
        first_name=username.title(), last_name='Tester', **extra,
    )


def make_student(username, school, counselor=None, assistant=None, grade='10'):
    user = make_user(username, User.Role.STUDENT, school)
    return StudentProfile.objects.create(
        user=user, school=school, school_name=school.name, assigned_counselor=counselor,
        assigned_assistant=assistant, grade=grade,
    )


@override_settings(BOT_SERVICE_KEY=KEY, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BotTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.school_a = School.objects.create(name='School A', code='bot-a')
        self.school_b = School.objects.create(name='School B', code='bot-b')
        self.c1 = make_user('counselor1', User.Role.COUNSELOR, self.school_a, phone='+998901112233')
        self.c2 = make_user('counselor2', User.Role.COUNSELOR, self.school_a)
        self.cb = make_user('counselorb', User.Role.COUNSELOR, self.school_b)
        self.a1 = make_user('assistant1', User.Role.ASSISTANT, self.school_a, supervising_counselor=self.c1)
        self.a2 = make_user('assistant2', User.Role.ASSISTANT, self.school_a, supervising_counselor=self.c2)
        self.s1 = make_student('stu1', self.school_a, self.c1, grade='9')
        self.s2 = make_student('stu2', self.school_a, self.c1, self.a1, grade='10')
        self.s3 = make_student('stu3', self.school_a, self.c2, self.a2, grade='10')
        self.s4 = make_student('stu4', self.school_b, self.cb, grade='11')
        self.chat = 1001

    def call(self, method, path, data=None, key=KEY):
        headers = {'HTTP_X_BOT_SERVICE_KEY': key} if key is not None else {}
        return getattr(self.client, method)(f'/api/bot/{path}/', data, format='json', **headers)

    def post(self, path, data=None, **kw):
        return self.call('post', path, data, **kw)

    def link(self, user, chat_id=None, language='uz'):
        chat_id = chat_id or self.chat
        login = self.post('login', {'chat_id': chat_id, 'username': user.username, 'password': PASSWORD})
        assert login.status_code == 200, login.content
        confirm = self.post('confirm', {
            'chat_id': chat_id, 'pending_token': login.json()['pending_token'], 'language': language,
        })
        assert confirm.status_code == 200, confirm.content
        return chat_id

    def names(self, response):
        return sorted(name for group in response.json()['groups'] for name in group['students'])
