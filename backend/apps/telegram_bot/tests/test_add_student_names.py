from apps.users.models import TemporaryCredential, User

from .base import BotTestCase


class AddStudentNameAndSchoolTests(BotTestCase):
    def body(self, full_name, email, phone, chat=None):
        return {'chat_id': chat or self.chat, 'full_name': full_name, 'email': email, 'phone': phone}

    def test_surname_first_is_saved_as_last_name(self):
        self.link(self.c1)
        body = self.post('add-student', self.body('Muzaffarova Manzura', 'manzura@example.com', '+998 90 111 22 33')).json()
        user = User.objects.get(username=body['username'])
        self.assertEqual((user.first_name, user.last_name), ('Manzura', 'Muzaffarova'))

    def test_given_name_first_is_kept(self):
        self.link(self.c1)
        body = self.post('add-student', self.body('Akbar Axmedov', 'akbar@example.com', '+998 90 111 22 34')).json()
        user = User.objects.get(username=body['username'])
        self.assertEqual((user.first_name, user.last_name), ('Akbar', 'Axmedov'))

    def test_duplicate_check_ignores_word_order(self):
        self.link(self.c1)
        first = self.post('add-student', self.body('Muzaffarova Manzura', 'a@example.com', '+998901112244'))
        self.assertEqual(first.status_code, 201, first.content)
        # The student has signed in since, so a repeat is a real duplicate, not a retry.
        TemporaryCredential.objects.filter(user__username=first.json()['username']).update(
            status=TemporaryCredential.Status.USED,
        )
        for name in ('Manzura Muzaffarova', 'Muzaffarova Manzura'):
            again = self.post('add-student', self.body(name, 'b@example.com', '90 111 22 44'))
            self.assertEqual(again.status_code, 409, again.content)
            self.assertEqual(again.json()['code'], 'student_exists')
        self.assertEqual(User.objects.filter(last_name='Muzaffarova').count(), 1)

    def test_success_payload_carries_the_callers_own_school(self):
        self.link(self.c1)
        body = self.post('add-student', self.body('Saydazimova Sofiya', 's@example.com', '+998 91 007 68 25')).json()
        self.assertEqual(body['school'], 'School A')

    def test_preview_gives_school_and_split_without_creating_anything(self):
        self.link(self.c1)
        before = User.objects.count()
        response = self.post('add-student/preview', {'chat_id': self.chat, 'full_name': 'Muzaffarova Manzura'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {'school': 'School A', 'first_name': 'Manzura', 'last_name': 'Muzaffarova'})
        self.assertEqual(User.objects.count(), before)

    def test_preview_shows_each_callers_own_school(self):
        self.link(self.cb, chat_id=555)
        response = self.post('add-student/preview', {'chat_id': 555, 'full_name': 'Ali Valiyev'})
        self.assertEqual(response.json()['school'], 'School B')

    def test_preview_needs_a_link_and_a_name(self):
        self.assertEqual(self.post('add-student/preview', {'chat_id': 999, 'full_name': 'Ali Valiyev'}).status_code, 404)
        self.link(self.c1)
        self.assertEqual(self.post('add-student/preview', {'chat_id': self.chat, 'full_name': '  '}).status_code, 400)
