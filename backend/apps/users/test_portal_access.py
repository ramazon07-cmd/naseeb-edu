from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from apps.admissions.models import School


class PrivatePortalAccessTests(APITestCase):
    def test_anonymous_visitors_cannot_read_private_resources(self):
        for endpoint in ('students', 'tasks', 'documents', 'essays', 'applications', 'message-channels'):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f'/api/{endpoint}/')
                self.assertEqual(response.status_code, 401)

    def test_registration_is_not_self_service_even_after_login(self):
        User = get_user_model()
        school = School.objects.create(name='Access test school', code='access-test')
        for role in (User.Role.STUDENT, User.Role.PARENT, User.Role.TEACHER, User.Role.COUNSELOR, User.Role.ORGANIZATION):
            with self.subTest(role=role):
                user = User.objects.create_user(username=f'access-{role}', email=f'access-{role}@example.test', role=role, school=school)
                self.client.force_authenticate(user)
                response = self.client.post('/api/users/register/', {
                    'username': f'created-by-{role}',
                    'email': f'{role}@example.test',
                    'password': 'A-strong-test-password-987!',
                    'role': User.Role.STUDENT,
                }, format='json')
                self.assertEqual(response.status_code, 403)
                self.assertFalse(User.objects.filter(username=f'created-by-{role}').exists())

    def test_anonymous_registration_is_rejected(self):
        response = self.client.post('/api/users/register/', {}, format='json')
        self.assertEqual(response.status_code, 401)
