from unittest import mock

from django.contrib.auth import authenticate

from apps.admissions.models import StudentProfile
from apps.telegram_bot import students as bot_students
from apps.users.models import ProductAuditEvent, TemporaryCredential, User
from apps.users.test_entitlements import use_plan

from .base import BotTestCase, make_user


class AddStudentTests(BotTestCase):
    def add(self, chat=None, **fields):
        payload = {
            'chat_id': chat or self.chat,
            'full_name': 'Saydazimova Sofiya',
            'email': '@saidazimova.safiiya@gmail.com',
            'phone': '+998 91 007 68 25',
            **fields,
        }
        return self.post('add-student', payload)

    def students_named(self, first_name):
        return StudentProfile.objects.filter(user__first_name=first_name)

    def test_counselor_adds_a_student_end_to_end(self):
        self.link(self.c1)
        response = self.add()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        profile = StudentProfile.objects.select_related('user').get(user__username=body['username'])
        student = profile.user
        self.assertEqual(body['username'], 'saydazimova-sofiya')
        self.assertEqual(body['full_name'], 'Saydazimova Sofiya')
        self.assertEqual(body['phone'], '+998910076825')
        self.assertNotIn('email', body)
        self.assertTrue(body['login_url'].endswith('/login'))
        self.assertEqual(student.role, User.Role.STUDENT)
        self.assertEqual(student.email, 'saidazimova.safiiya@gmail.com')
        self.assertEqual(student.phone, '+998910076825')
        self.assertEqual(profile.school, self.school_a)
        self.assertEqual(profile.assigned_counselor, self.c1)
        self.assertTrue(student.must_change_password)
        credential = TemporaryCredential.objects.get(user=student)
        self.assertEqual(credential.status, TemporaryCredential.Status.ISSUED)
        self.assertEqual(credential.issued_by, self.c1)
        self.assertEqual(body['expires_at'], credential.expires_at.isoformat())
        # The password handed back is the one that works, by username and by email.
        self.assertEqual(authenticate(username=body['username'], password=body['temporary_password']), student)
        self.assertTrue(ProductAuditEvent.objects.filter(
            action='student.created_via_bot', actor=self.c1, target_id=str(student.pk),
        ).exists())
        # And the counselor sees the new student in the bot right away.
        names = self.names(self.post('students', {'chat_id': self.chat}))
        self.assertIn('Saydazimova Sofiya', names)

    def test_assistant_adds_a_student_for_their_counselor(self):
        self.link(self.a1)
        response = self.add()

        self.assertEqual(response.status_code, 201, response.content)
        profile = StudentProfile.objects.get(user__username=response.json()['username'])
        self.assertEqual(profile.assigned_counselor, self.c1)
        self.assertEqual(profile.assigned_assistant, self.a1)
        self.assertIn('Saydazimova Sofiya', self.names(self.post('students', {'chat_id': self.chat})))

    def test_bad_input_is_refused_and_nothing_is_saved(self):
        self.link(self.c1)
        before = StudentProfile.objects.count()
        for fields, code in (
            ({'email': 'not-an-email'}, 'invalid_email'),
            ({'phone': '12345'}, 'invalid_phone'),
            ({'full_name': '   '}, 'invalid_name'),
            ({'full_name': 'x' * 151}, 'invalid_name'),
        ):
            response = self.add(**fields)
            self.assertEqual(response.status_code, 400, fields)
            self.assertEqual(response.json()['code'], code, fields)
        self.assertEqual(StudentProfile.objects.count(), before)

    def test_sending_the_same_student_twice_does_not_make_a_second_account(self):
        self.link(self.c1)
        first = self.add()
        self.assertEqual(first.status_code, 201)
        # Same phone typed differently, other email.
        again = self.add(email='other@example.com', phone='91 007-68-25')
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()['code'], 'student_exists')
        self.assertEqual(again.json()['username'], first.json()['username'])
        self.assertEqual(self.students_named('Saydazimova').count(), 1)

    def test_another_counselors_student_is_not_revealed(self):
        self.link(self.c2)
        response = self.add(full_name='Someone Else', email=self.s1.user.email, phone='+998 90 000 00 01')
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body['code'], 'student_exists_elsewhere')
        self.assertEqual(set(body) - {'detail'}, {'code'})

    def test_an_email_used_at_another_school_still_creates_the_student(self):
        make_user('outsider', User.Role.STUDENT, self.school_b, phone='+998900000002')
        self.link(self.c1)
        response = self.add(email='outsider@example.com')
        self.assertEqual(response.status_code, 201)
        student = User.objects.get(username=response.json()['username'])
        # Same as quick-create: a placeholder address, and the answer does not say so.
        self.assertNotEqual(student.email, 'outsider@example.com')
        self.assertNotIn('outsider', response.content.decode())

    def test_seat_limit(self):
        use_plan(self.school_a, max_students=3)
        self.link(self.c1)
        response = self.add()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'seat_limit')
        self.assertFalse(self.students_named('Saydazimova').exists())

    def test_hourly_limit_per_chat(self):
        self.link(self.c1)
        with mock.patch.object(bot_students, 'ADDS_PER_HOUR', 1):
            self.assertEqual(self.add().status_code, 201)
            response = self.add(full_name='Second Student', email='second@example.com', phone='+998900000003')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['code'], 'too_many')

    def test_unlinked_chat_and_missing_key(self):
        self.assertEqual(self.add(chat=4242).json()['code'], 'not_linked')
        self.link(self.c1)
        response = self.call('post', 'add-student', {
            'chat_id': self.chat, 'full_name': 'A B', 'email': 'a@b.uz', 'phone': '+998900000004',
        }, key=None)
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(self.students_named('A').exists())


class PhoneTests(BotTestCase):
    def test_normalize_phone(self):
        for raw, expected in (
            ('+998 91 007 68 25', '+998910076825'),
            ('91-007-68-25', '+998910076825'),
            ('(91) 007 68 25', '+998910076825'),
            ('998910076825', '+998910076825'),
            ('+7 916 123 45 67', '+79161234567'),
        ):
            self.assertEqual(bot_students.normalize_phone(raw), expected)
