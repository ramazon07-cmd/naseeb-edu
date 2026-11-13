from django.contrib.auth import authenticate
from django.utils import timezone

from apps.users.models import ProductAuditEvent, TemporaryCredential, User

from .base import PASSWORD, BotTestCase


class FindStudentsTests(BotTestCase):
    def find(self, query, chat=None):
        return self.post('find-students', {'chat_id': chat or self.chat, 'query': query})

    def test_counselor_finds_only_their_own_students(self):
        self.link(self.c1)
        response = self.find('stu')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([row['username'] for row in body['students']], ['stu1', 'stu2'])
        self.assertEqual(body['students'][0], {'id': self.s1.pk, 'full_name': 'Stu1 Tester', 'username': 'stu1'})
        self.assertFalse(body['more'])

    def test_every_word_must_match(self):
        self.link(self.c1)
        self.assertEqual([r['username'] for r in self.find('stu2 tester').json()['students']], ['stu2'])
        self.assertEqual(self.find('stu3').json()['students'], [])

    def test_assistant_finds_only_their_students(self):
        self.link(self.a1)
        self.assertEqual([r['username'] for r in self.find('stu').json()['students']], ['stu2'])

    def test_deactivated_students_are_left_out(self):
        self.s1.deactivated_at = timezone.now()
        self.s1.save(update_fields=['deactivated_at'])
        self.link(self.c1)
        self.assertEqual([r['username'] for r in self.find('stu').json()['students']], ['stu2'])

    def test_short_query_and_unlinked_chat_are_refused(self):
        self.link(self.c1)
        self.assertEqual(self.find(' a ').json()['code'], 'invalid_query')
        self.assertEqual(self.find('stu', chat=999).status_code, 404)


class ResetPasswordTests(BotTestCase):
    def reset(self, student_id, chat=None):
        return self.post('reset-password', {'chat_id': chat or self.chat, 'student_id': student_id})

    def test_counselor_resets_a_students_password_end_to_end(self):
        self.link(self.c1)
        response = self.reset(self.s1.pk)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        student = User.objects.get(pk=self.s1.user_id)
        self.assertEqual(body['username'], 'stu1')
        self.assertEqual(body['full_name'], 'Stu1 Tester')
        self.assertTrue(body['login_url'].endswith('/login'))
        self.assertNotIn('phone', body)
        # The new password works, the old one does not, and the student must set their own.
        self.assertEqual(authenticate(username='stu1', password=body['temporary_password']), student)
        self.assertIsNone(authenticate(username='stu1', password=PASSWORD))
        self.assertTrue(student.must_change_password)
        credential = TemporaryCredential.objects.get(user=student)
        self.assertEqual(credential.status, TemporaryCredential.Status.ISSUED)
        self.assertEqual(credential.issued_by, self.c1)
        self.assertEqual(body['expires_at'], credential.expires_at.isoformat())
        event = ProductAuditEvent.objects.get(action='credential.issued', target_id=str(student.pk))
        self.assertEqual(event.actor, self.c1)
        self.assertEqual(event.metadata.get('via'), 'bot')

    def test_a_second_reset_revokes_the_first_password(self):
        self.link(self.c1)
        first = self.reset(self.s1.pk).json()['temporary_password']
        second = self.reset(self.s1.pk).json()['temporary_password']
        self.assertIsNone(authenticate(username='stu1', password=first))
        self.assertIsNotNone(authenticate(username='stu1', password=second))
        statuses = sorted(TemporaryCredential.objects.filter(user=self.s1.user).values_list('status', flat=True))
        self.assertEqual(statuses, sorted([TemporaryCredential.Status.ISSUED, TemporaryCredential.Status.REVOKED]))

    def test_assistant_resets_their_own_students_only(self):
        self.link(self.a1)
        self.assertEqual(self.reset(self.s2.pk).status_code, 200)
        self.assertEqual(self.reset(self.s1.pk).json()['code'], 'student_not_found')

    def test_students_out_of_reach_are_not_found_and_untouched(self):
        self.link(self.c1)
        for profile in (self.s3, self.s4):  # another counselor's, another school's
            response = self.reset(profile.pk)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()['code'], 'student_not_found')
            self.assertIsNotNone(authenticate(username=profile.user.username, password=PASSWORD))
        self.assertEqual(self.reset(999999).status_code, 404)
        self.assertFalse(TemporaryCredential.objects.exists())

    def test_deactivated_student_is_not_reset(self):
        self.s1.user.is_active = False
        self.s1.user.save(update_fields=['is_active'])
        self.link(self.c1)
        self.assertEqual(self.reset(self.s1.pk).status_code, 404)

    def test_bad_id_and_unlinked_chat_are_refused(self):
        self.link(self.c1)
        for value in ('1', True, None):
            self.assertEqual(self.reset(value).status_code, 400, value)
        self.assertEqual(self.reset(self.s1.pk, chat=999).status_code, 404)
        self.assertEqual(self.reset(self.s1.pk, chat=999).json()['code'], 'not_linked')

    def test_resets_are_rate_limited(self):
        from apps.telegram_bot import students

        self.link(self.c1)
        original = students.RESETS_PER_HOUR
        students.RESETS_PER_HOUR = 2
        try:
            codes = [self.reset(self.s1.pk).status_code for _ in range(3)]
        finally:
            students.RESETS_PER_HOUR = original
        self.assertEqual(codes, [200, 200, 429])
