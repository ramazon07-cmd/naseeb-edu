from apps.users.models import User

from ..models import StudentProfile
from .base import RoleIsolationBase

URL = '/api/students/quick-create/'


class QuickCreateDuplicateTests(RoleIsolationBase):
    def add(self, **fields):
        payload = {'name': 'Ali Valiyev', 'email': 'ali.valiyev@gmail.com', 'phone': '+998 90 123 45 67', **fields}
        return self.client.post(URL, payload, format='json')

    def test_the_same_student_twice_is_refused_with_the_existing_login(self):
        self.client.force_authenticate(self.counselor)
        first = self.add()
        self.assertEqual(first.status_code, 201, first.data)
        # Same phone typed differently, other email.
        again = self.add(email='other@example.com', phone='901234567')
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data['code'], 'student_exists')
        self.assertEqual(again.data['username'], 'ali-valiyev')
        # Same email, no placeholder twin either.
        self.assertEqual(self.add(phone='+998 99 000 00 00').status_code, 409)
        self.assertEqual(StudentProfile.objects.filter(user__first_name='Ali').count(), 1)

    def test_another_counselors_student_is_not_named(self):
        other = User.objects.create_user(
            username='counselor-two', email='c2@example.com', password='x-Strong-Pass-1', role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        self.client.force_authenticate(other)
        self.assertEqual(self.add().status_code, 201)
        self.client.force_authenticate(self.counselor)
        response = self.add()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'student_exists_elsewhere')
        self.assertNotIn('username', response.data)

    def test_an_email_used_at_another_school_still_creates_the_student(self):
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.add().status_code, 201)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.add(phone='+998 91 111 22 33').status_code, 201)
