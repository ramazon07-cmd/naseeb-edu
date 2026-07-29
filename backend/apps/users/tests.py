from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.admissions.models import School, StudentProfile


User = get_user_model()


class StudentAdminCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-test',
            email='admin-test@example.com',
            password='StrongAdminPass123!',
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(name='Rustam Bosimov School', code='rbis-test')
        self.client.force_login(self.admin)

    def test_admin_created_student_gets_profile_with_initial_level(self):
        response = self.client.post(reverse('admin:users_user_add'), {
            'username': 'new-student',
            'password1': 'StrongStudentPass123!',
            'password2': 'StrongStudentPass123!',
            'first_name': 'Muhammadrasul',
            'last_name': 'Kipchakov',
            'email': 'new-student@example.com',
            'role': User.Role.STUDENT,
            'school': self.school.id,
            'phone': '',
            'position': '',
            '_save': 'Save',
        })

        self.assertEqual(response.status_code, 302)
        student_user = User.objects.get(username='new-student')
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(profile.school, self.school)
        self.assertEqual(profile.school_name, self.school.name)
        self.assertEqual(profile.level, 1)
        self.assertEqual(profile.xp_total, 0)
