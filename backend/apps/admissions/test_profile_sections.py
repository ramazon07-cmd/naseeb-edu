"""Editing one profile section at a time (PATCH /api/students/onboarding/)."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.users.models import User
from .models import School, StudentProfile
from .onboarding import PROFILE_READINESS_ITEMS, profile_readiness

URL = '/api/students/onboarding/'


class ProfileSectionEditTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Section school', code='section-test')
        self.student = User.objects.create_user(username='section-student', email='section-student@example.com', role='student', school=self.school)
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school)
        self.client.force_authenticate(self.student)
        self.payload = dict(
            first_name='Aziza', last_name='Karimova', gender='Female', grade='11', graduation_year=2027,
            family_income='Under $10,000', guardian_name='Dilnoza', guardian_relation='mother', guardian_contact='+998901112233',
            school_name='Section school', country='Uzbekistan', city='Tashkent', class_size=25, class_rank=3,
            gpa_scale='5', gpa=4.6, ielts_status='taken', ielts_score=7, ielts_listening=7.5, ielts_reading=7,
            ielts_writing=6.5, ielts_speaking=7, ielts_test_date='2026-03-14', ielts_attempts=2,
            target_countries='US, UK', interests=['Computer Technologies'], personal_story='I build robots.',
            honors=[dict(role='Captain', project='Robotics club', description='Led the team.', recognition='National')],
            activities=[dict(type='Club', position='Captain', organization='Robotics', description='Weekly builds.', grades='10-11', hours=4, weeks=30)],
        )
        response = self.client.post(URL, self.payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()

    def patch(self, body):
        return self.client.patch(URL, body, format='json')

    def test_editing_one_section_keeps_every_other_answer(self):
        before = dict(self.profile.application_profile)
        response = self.patch({'target_countries': 'Canada', 'interests': ['Engineering', 'Science'], 'program_strengths': [], 'personal_story': 'New story.'})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.target_countries, 'Canada')
        self.assertEqual(self.profile.target_major, 'Engineering, Science')
        answers = self.profile.application_profile
        self.assertEqual((answers['interests'], answers['personal_story']), (['Engineering', 'Science'], 'New story.'))
        for key in ('gender', 'city', 'class_size', 'honors', 'activities', 'graduation_year', 'family_income'):
            self.assertEqual(answers[key], before[key], key)
        self.assertEqual((self.profile.ielts_score, self.profile.ielts_listening, self.profile.gpa), (Decimal('7.0'), Decimal('7.5'), Decimal('4.60')))
        self.assertEqual(self.profile.guardian_name, 'Dilnoza')
        self.assertIsNotNone(self.profile.profile_completed_at)
        self.assertEqual(response.data['profile']['target_countries'], 'Canada')

    def test_only_the_sent_fields_are_validated(self):
        # A required onboarding answer that is absent from the PATCH is not an error.
        response = self.patch({'city': 'Samarkand'})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.application_profile['city'], self.profile.application_profile['country']), ('Samarkand', 'Uzbekistan'))
        response = self.patch({'city': '', 'graduation_year': 1900})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data) - {'detail'}, {'city', 'graduation_year'})

    def test_required_answers_cannot_be_cleared(self):
        for body in ({'first_name': ''}, {'gpa': None}, {'target_countries': ''}, {'gender': ''}):
            self.assertEqual(self.patch(body).status_code, 400, body)
        self.profile.refresh_from_db()
        self.assertEqual((self.student.first_name, self.profile.gpa), ('Aziza', Decimal('4.60')))

    def test_ielts_sections_are_checked_against_the_stored_overall(self):
        response = self.patch({'ielts_listening': 9})
        self.assertEqual(response.status_code, 400)
        self.assertIn('overall band is 7.5', str(response.data['ielts_score']))
        response = self.patch({'ielts_listening': 9, 'ielts_score': 7.5})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.ielts_score, self.profile.ielts_listening, self.profile.ielts_attempts), (Decimal('7.5'), Decimal('9.0'), 2))

    def test_gpa_is_checked_against_the_stored_scale(self):
        response = self.patch({'gpa': 4.9})
        self.assertEqual(response.status_code, 200, response.data)
        response = self.patch({'gpa': 5.5})
        self.assertEqual(response.status_code, 400)
        self.assertIn('gpa', response.data)
        response = self.patch({'gpa_scale': '4'})
        self.assertEqual(response.status_code, 400, 'the stored 4.9 does not fit a 4-point scale')
        response = self.patch({'class_rank': 30})
        self.assertEqual(response.status_code, 400)
        self.assertIn('class_rank', response.data)

    def test_sat_edit_computes_the_total_and_leaves_ielts_alone(self):
        response = self.patch({'sat_status': 'taken', 'sat_reading': 650, 'sat_math': 700, 'sat_test_date': '2026-05-02', 'sat_attempts': 2, 'sat_superscore': True, 'sat_superscore_reading': 690, 'sat_superscore_math': 720})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.sat_score, self.profile.ielts_score), (1410, Decimal('7.0')))
        response = self.patch({'sat_superscore_math': 690})
        self.assertEqual(response.status_code, 400)
        self.assertIn('sat_superscore_math', response.data)

    def test_switching_ielts_to_planning_clears_its_scores(self):
        response = self.patch({'ielts_status': 'planning', 'ielts_test_date': '2027-01-10'})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.ielts_status, self.profile.ielts_score, self.profile.ielts_listening), ('planning', None, None))

    def test_nested_rows_are_validated(self):
        response = self.patch({'honors': [dict(role='', project='x', description='y', recognition='Galactic')]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('honors', response.data)
        response = self.patch({'honors': []})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.application_profile['honors'], [])
        self.assertEqual(len(self.profile.application_profile['activities']), 1)

    def test_guardian_contact_can_be_cleared(self):
        response = self.patch({'guardian_contact': ''})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.parent_contact, '')

    def test_staff_only_fields_are_ignored(self):
        response = self.patch({'city': 'Bukhara', 'xp_total': 5000, 'level': 9, 'notes': 'x', 'user': 999, 'school': 999})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.xp_total, self.profile.level, self.profile.notes, self.profile.school_id, self.profile.user_id), (0, 1, '', self.school.id, self.student.id))

    def test_empty_patch_is_rejected(self):
        self.assertEqual(self.patch({}).status_code, 400)

    def test_patch_requires_a_completed_profile(self):
        other = User.objects.create_user(username='section-new', email='section-new@example.com', role='student', school=self.school)
        StudentProfile.objects.create(user=other, school=self.school)
        self.client.force_authenticate(other)
        response = self.patch({'city': 'Tashkent'})
        self.assertEqual(response.status_code, 400)

    def test_only_the_student_edits_their_own_profile(self):
        counselor = User.objects.create_user(username='section-counselor', email='section-counselor@example.com', role='counselor', school=self.school)
        parent = User.objects.create_user(username='section-parent', email='section-parent@example.com', role='parent')
        for user in (counselor, parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.patch({'city': 'Nukus'}).status_code, 403, user.role)
        other_school = School.objects.create(name='Other school', code='section-other')
        stranger = User.objects.create_user(username='section-stranger', email='section-stranger@example.com', role='student', school=other_school)
        stranger_profile = StudentProfile.objects.create(user=stranger, school=other_school)
        StudentProfile.objects.filter(pk=stranger_profile.pk).update(profile_completed_at=self.profile.profile_completed_at)
        self.client.force_authenticate(stranger)
        self.assertEqual(self.patch({'city': 'Nukus'}).status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.application_profile['city'], 'Tashkent')

    def test_patch_query_count_is_bounded(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.patch({'city': 'Fergana'}).status_code, 200)
        self.assertLessEqual(len(queries), 14, [q['sql'] for q in queries])


class ProfileReadinessTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Ready school', code='ready-test')
        self.student = User.objects.create_user(username='ready-student', email='ready@example.com', role='student', school=self.school)
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school, school_name='')

    def test_empty_profile_lists_every_item(self):
        readiness = profile_readiness(self.profile)
        self.assertEqual(readiness['percent'], 0)
        self.assertEqual([item['key'] for item in readiness['missing']], [key for key, _, _ in PROFILE_READINESS_ITEMS])

    def test_answered_items_raise_the_percent(self):
        self.profile.gpa = Decimal('4.5')
        self.profile.target_countries = 'US'
        self.profile.ielts_status = 'planning'
        self.profile.application_profile = {'interests': ['Arts'], 'activities': [{'type': 'Club'}]}
        readiness = profile_readiness(self.profile)
        # 5 of 12 answered: 41.67% rounds to 42.
        self.assertEqual(readiness['percent'], 42)
        missing = {item['key']: item['section'] for item in readiness['missing']}
        self.assertEqual(missing['sat'], 'tests')
        self.assertNotIn('gpa', missing)

    def test_readiness_is_served_with_the_profile(self):
        self.client.force_authenticate(self.student)
        data = self.client.get(URL).data
        self.assertEqual(data['profile_readiness']['percent'], 0)
        listed = self.client.get('/api/students/').data
        rows = listed['results'] if isinstance(listed, dict) else listed
        self.assertIn('profile_readiness', rows[0])
