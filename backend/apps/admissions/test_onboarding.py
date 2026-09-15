from rest_framework.test import APITestCase
from apps.users.models import User
from apps.users.serializers import UserSerializer
from .models import School, StudentProfile

class StudentOnboardingTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Test school', code='onboarding-test')
        self.student = User.objects.create_user(username='onboarding-student', email='onboarding-student@example.com', role='student', school=self.school)
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school)
        self.counselor = User.objects.create_user(username='onboarding-counselor', email='onboarding-counselor@example.com', role='counselor', school=self.school)
        self.profile.assigned_counselor = self.counselor
        self.profile.save()
        self.client.force_authenticate(self.student)
        self.payload = dict(first_name='Student', last_name='Example', gender='Male', grade='11', graduation_year=2027,
            family_income='Under $10,000', school_name='Test school', country='Uzbekistan', city='Tashkent',
            class_size=25, gpa_scale='5', gpa=4.8, ielts_status='not_taken', target_countries='US',
            honors=[dict(role='Coordinator', project='Community project', description='Organized weekly events.', recognition='School')])

    def test_completion_persists_profile_and_unlocks_user(self):
        self.assertFalse(UserSerializer(self.student).data['student_profile_complete'])
        response = self.client.post('/api/students/onboarding/', self.payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['user']['student_profile_complete'])
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.profile_completed_at)
        self.assertEqual(self.profile.application_profile['honors'][0]['project'], 'Community project')
        self.assertEqual(self.client.get('/api/students/onboarding/').data['application_profile']['family_income'], 'Under $10,000')

    def test_required_income_and_gpa(self):
        for field in ['family_income', 'gpa']:
            payload = dict(self.payload); payload.pop(field)
            response = self.client.post('/api/students/onboarding/', payload, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.profile_completed_at)

    def test_score_ranges_and_countries(self):
        for values, error in [({'gpa': 6}, 'gpa'), ({'sat_math': 900}, 'sat_math'), ({'target_countries': 'Unknown'}, 'target_countries'), ({'ielts_status': 'taken'}, 'ielts_score')]:
            response = self.client.post('/api/students/onboarding/', {**self.payload, **values}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn(error, response.data)

    def test_hundred_point_gpa(self):
        response = self.client.post('/api/students/onboarding/', {**self.payload, 'gpa_scale': '100', 'gpa': 100}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_counselor_cannot_complete_or_edit_profile(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post('/api/students/onboarding/', self.payload, format='json').status_code, 403)
        response = self.client.patch(f'/api/students/{self.profile.id}/', {'gpa': 5}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_client_cannot_override_ownership_or_completion(self):
        other = User.objects.create_user(username='other-onboarding', email='other-onboarding@example.com', role='student')
        response = self.client.post('/api/students/onboarding/', {**self.payload, 'user': other.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.user_id, self.student.pk)
        self.assertFalse(StudentProfile.objects.filter(user=other).exists())

    def test_login_creation_ignores_student_details(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/students/quick-create/', {'name': 'New Student', 'password': 'ZebRa!42', 'gpa': 5, 'countries': 'US'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['school'], self.school.pk)
        self.assertIsNone(response.data['gpa'])
        self.assertFalse(response.data['user_detail']['student_profile_complete'])
        self.assertTrue(response.data['user_detail']['must_change_password'])

    def test_optional_sat_and_multiple_countries(self):
        response = self.client.post('/api/students/onboarding/', {
            **self.payload, 'target_countries': 'Canada, Hong Kong, Canada',
            'sat_status': 'not_taken', 'sat_reading': None, 'sat_math': None,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.sat_score)
        self.assertEqual(self.profile.target_countries, 'Canada, Hong Kong')

    def test_available_sat_requires_both_sections(self):
        response = self.client.post('/api/students/onboarding/', {
            **self.payload, 'sat_status': 'taken', 'sat_reading': 700,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('sat_math', response.data)
