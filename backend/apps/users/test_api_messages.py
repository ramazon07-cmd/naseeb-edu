import ast
import re
import string
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from . import api_messages
from .localization import localized_api_error
from .models import User

ADMISSIONS = Path(__file__).resolve().parent.parent / 'admissions'


class ApiMessageTableTests(SimpleTestCase):
    def test_every_message_has_uzbek_and_russian_text(self):
        for english, translations in api_messages.EXACT.items():
            for language in ('uz', 'ru'):
                self.assertTrue(translations.get(language), f'{language}: {english}')
                self.assertNotEqual(translations[language], english)

    def test_pattern_templates_only_use_their_groups(self):
        for pattern, templates in api_messages.PATTERNS:
            for language in ('uz', 'ru'):
                fields = [name for _, name, _, _ in string.Formatter().parse(templates[language]) if name is not None]
                self.assertTrue(all(name.isdigit() and int(name) < pattern.groups for name in fields), pattern.pattern)

    def test_parametrised_messages_keep_their_numbers(self):
        cases = {
            'Ensure this field has no more than 220 characters.': ('220', '220'),
            'File is larger than the 20 MB limit.': ('20 MB', '20 МБ'),
            'Enter a number from 1 to 10.': ('10', '10'),
            'This password is too short. It must contain at least 8 characters.': ('8', '8'),
        }
        for english, (uz, ru) in cases.items():
            self.assertIn(uz, localized_api_error(english, 400, language='uz'))
            self.assertIn(ru, localized_api_error(english, 400, language='ru'))
            self.assertEqual(localized_api_error(english, 400, language='en'), english)

    def test_throttle_wait_is_translated_with_its_message(self):
        text = 'Request was throttled. Expected available in 42 seconds.'
        self.assertEqual(localized_api_error(text, 429, language='ru'), 'Слишком много запросов. Повторите через 42 с.')
        self.assertIn('42', localized_api_error(text, 429, language='uz'))

    def test_unknown_message_falls_back_to_the_status_message(self):
        self.assertEqual(
            localized_api_error('Something new went wrong.', 400, language='uz'),
            'So‘rovni bajarib bo‘lmadi. Kiritilgan ma’lumotlarni tekshiring.',
        )

    def test_student_profile_form_messages_are_all_translated(self):
        # Every fixed sentence the profile form (onboarding.py) can answer with.
        tree = ast.parse((ADMISSIONS / 'onboarding.py').read_text())
        sentences = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and re.fullmatch(r'[A-Z][^\n]{8,}[.]', node.value) and ' ' in node.value
            and not node.value.startswith(('Student-owned', 'The stored', 'Share of', 'The SAT total'))
        }
        self.assertGreater(len(sentences), 20)
        for sentence in sorted(sentences):
            for language in ('uz', 'ru'):
                self.assertIsNotNone(api_messages.translate(sentence, language), f'{language}: {sentence}')


class StudentApiErrorLanguageTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Language school', code='language-school')
        self.student = User.objects.create_user(
            username='language-student', email='language-student@example.com', password='Correct-pass-123',
            role='student', school=self.school,
        )
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school)

    def test_wrong_password_is_explained_in_the_request_language(self):
        expected = {'en': 'No active account found with the given credentials', 'ru': 'Неверный логин или пароль.', 'uz': 'Login yoki parol noto‘g‘ri.'}
        for language, detail in expected.items():
            response = self.client.post(
                '/api/auth/token/', {'username': self.student.username, 'password': 'wrong-password'},
                format='json', HTTP_ACCEPT_LANGUAGE=language,
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(str(response.data['detail']), detail)

    def test_meeting_form_field_errors_are_specific_not_generic(self):
        self.client.force_authenticate(self.student)
        payload = {'topic': 'x' * 500, 'duration_minutes': 'abc'}
        response = self.client.post('/api/bookings/', payload, format='json', HTTP_ACCEPT_LANGUAGE='ru-RU,ru;q=0.9')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['starts_at'], ['Это поле обязательно.'])
        self.assertEqual(response.data['topic'], ['Не более 220 символов.'])
        self.assertEqual(response.data['duration_minutes'], ['Введите целое число.'])
        self.assertEqual(response['Content-Language'], 'ru')

        response = self.client.post('/api/bookings/', payload, format='json', HTTP_ACCEPT_LANGUAGE='uz')
        self.assertEqual(response.data['starts_at'], ['Bu maydonni to‘ldirish shart.'])
        self.assertEqual(response.data['topic'], ['220 belgidan oshmasin.'])

    def test_english_field_errors_are_unchanged(self):
        self.client.force_authenticate(self.student)
        response = self.client.post('/api/bookings/', {'topic': 'x' * 500}, format='json', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.data['topic'], ['Ensure this field has no more than 220 characters.'])
        self.assertEqual(response.data['starts_at'], ['This field is required.'])

    def test_profile_photo_error_is_translated(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/students/{self.profile.pk}/photo/', {}, HTTP_ACCEPT_LANGUAGE='uz')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data['photo'], 'Yuklash uchun rasm tanlang.')


# Admin-portal errors the provisioning, school and roadmap screens can show.
ADMIN_MESSAGES = (
    'You cannot delete your own account.',
    'You cannot deactivate your own account.',
    'Temporary credentials are only available for student and school accounts.',
    'You cannot issue credentials for this account.',
    'Only a product admin can create counselors.',
    'Only a product admin can create individual counselors.',
    'Only a product admin can transfer counselors.',
    'Only counselor accounts can be transferred.',
    'Select an active organization school.',
    'Reassign or move the counselor’s students before transferring the counselor.',
    'Only a product admin can deactivate accounts.',
    'Only product staff can open a support view.',
    'Only a product admin can activate or deactivate accounts.',
    'Only a product admin can change user roles.',
    'Only a super admin can grant or remove product admin access.',
    'Only a super admin can change staff access levels.',
    'This username is already in use.',
    'This email is already in use.',
    'The period cannot end before it starts.',
    'An individual counselor workspace has no school or teacher accounts.',
    'An individual counselor workspace has no school accounts.',
    'This workspace is read-only until its subscription is renewed.',
    'This workspace plan does not include this feature.',
    'This workspace setting cannot be changed after creation.',
    'Only a product admin can create schools.',
    'Only a product admin can edit schools.',
    'Only a product admin can deactivate schools.',
    'Only a product admin can create organization accounts.',
    'Only a product admin can create roadmap templates.',
    'Only a product admin can review counselor missions.',
    'This workspace plan allows at most 3 active counselors.',
    'This workspace plan allows at most 50 active student accounts.',
    'This workspace plan allows at most 0 active teachers.',
)


class AdminApiErrorLanguageTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Seat school', code='seat-school')
        self.other = School.objects.create(name='Other seat school', code='other-seat-school')
        self.ops = User.objects.create_user(
            username='seat-ops', email='seat-ops@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.OPS,
        )
        self.counselors = [
            User.objects.create_user(
                username=f'seat-counselor-{index}', email=f'seat-counselor-{index}@example.com',
                password='StrongPass123!', role=User.Role.COUNSELOR, school=self.school,
            )
            for index in range(3)
        ]
        self.client.force_authenticate(self.ops)

    def fourth_counselor(self, language):
        return self.client.post('/api/users/accounts/create-counselor/', {
            'username': 'seat-fourth', 'email': 'seat-fourth@example.com', 'first_name': 'Fourth',
            'password': 'StrongPass123!', 'school': self.school.id,
        }, format='json', HTTP_ACCEPT_LANGUAGE=language)

    def test_admin_messages_have_uzbek_and_russian_text(self):
        for message in ADMIN_MESSAGES:
            for language in ('uz', 'ru'):
                self.assertIsNotNone(api_messages.translate(message, language), f'{language}: {message}')

    def test_the_seat_limit_is_explained_in_uzbek_with_its_number(self):
        response = self.fourth_counselor('uz')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Ish maydoni tarifi ko‘pi bilan 3 ta faol maslahatchiga ruxsat beradi.')

    def test_english_admin_errors_read_as_before(self):
        response = self.fourth_counselor('en')
        self.assertEqual(response.data['detail'], 'This workspace plan allows at most 3 active counselors.')

    def test_a_blocked_transfer_is_explained_in_russian_with_its_code(self):
        student = User.objects.create_user(
            username='seat-student', email='seat-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        StudentProfile.objects.create(user=student, school=self.school, assigned_counselor=self.counselors[0])
        response = self.client.post(
            f'/api/users/accounts/{self.counselors[0].id}/transfer-school/', {'school': self.other.id},
            format='json', HTTP_ACCEPT_LANGUAGE='ru',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['detail'], 'Перед переводом консультанта переназначьте или переведите его учеников.')
        self.assertEqual(response.data['code'], 'counselor_has_students')
