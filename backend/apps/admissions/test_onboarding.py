import importlib

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase
from apps.users.models import User
from apps.users.serializers import UserSerializer
from .exam_scores import IELTS_FIELDS, SAT_FIELDS
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

    def test_family_income_is_optional(self):
        for payload in ({k: v for k, v in self.payload.items() if k != 'family_income'}, {**self.payload, 'family_income': ''}):
            response = self.client.post('/api/students/onboarding/', payload, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.profile_completed_at)
        invalid = self.client.post('/api/students/onboarding/', {**self.payload, 'family_income': 'a lot'}, format='json')
        self.assertEqual(invalid.status_code, 400)

    def test_required_income_and_gpa(self):
        for field in ['gpa']:
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


class GpaScaleTests(APITestCase):
    """The GPA scale chosen in onboarding is stored and honoured everywhere."""

    setUp = StudentOnboardingTests.setUp

    def test_onboarding_stores_scale_and_research_accepts_hundred_point_gpa(self):
        response = self.client.post('/api/students/onboarding/', {**self.payload, 'gpa_scale': '100', 'gpa': 92}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.gpa_scale, 100)
        research = self.client.post('/api/college-research/', {
            'sat_score': 1400, 'ielts_score': 7, 'target_major': 'Computer Science',
            'target_countries': 'USA', 'budget_usd': 20000,
        }, format='json')
        self.assertEqual(research.status_code, 200, research.data)
        self.assertEqual(research.data['profile_snapshot']['gpa_scale'], 100)

    def test_gpa_above_stored_scale_is_rejected(self):
        self.profile.gpa_scale = 4
        self.profile.gpa = 3.5
        self.profile.save()
        response = self.client.patch(f'/api/students/{self.profile.id}/', {'gpa': 4.6}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('gpa', response.data)
        ok = self.client.patch(f'/api/students/{self.profile.id}/', {'gpa': 4.6, 'gpa_scale': 5}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)

    def test_research_update_on_hundred_scale(self):
        response = self.client.post('/api/college-research/', {'gpa': 88, 'gpa_scale': 100}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((float(self.profile.gpa), self.profile.gpa_scale), (88.0, 100))
        too_high = self.client.post('/api/college-research/', {'gpa': 4.5, 'gpa_scale': 4}, format='json')
        self.assertEqual(too_high.status_code, 400)


class TestScoreOnboardingTests(APITestCase):
    """IELTS and SAT detail: validation, storage in columns and display to staff."""

    setUp = StudentOnboardingTests.setUp

    def post(self, **values):
        return self.client.post('/api/students/onboarding/', {**self.payload, **values}, format='json')

    ielts = dict(ielts_status='taken', ielts_score=6.5, ielts_listening=7, ielts_reading=6.5, ielts_writing=6,
                 ielts_speaking=6.5, ielts_test_date='2026-03-14', ielts_attempts=2)
    sat = dict(sat_status='taken', sat_reading=650, sat_math=700, sat_test_date='2026-05-02', sat_attempts=1)

    def test_ielts_with_sections_is_stored_in_columns(self):
        response = self.post(**self.ielts)
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual(
            [str(getattr(self.profile, name)) for name in ('ielts_score', 'ielts_listening', 'ielts_reading', 'ielts_writing', 'ielts_speaking')],
            ['6.5', '7.0', '6.5', '6.0', '6.5'],
        )
        self.assertEqual((self.profile.ielts_status, str(self.profile.ielts_test_date), self.profile.ielts_attempts), ('taken', '2026-03-14', 2))
        # One copy of each answer: nothing about tests is left in the JSON blob.
        self.assertFalse({'ielts_score', 'ielts_status', 'sat_status'} & set(self.profile.application_profile))
        detail = self.client.get('/api/students/onboarding/').data
        self.assertEqual((detail['ielts_listening'], detail['ielts_attempts']), ('7.0', 2))

    def test_ielts_overall_must_match_sections(self):
        response = self.post(**{**self.ielts, 'ielts_score': 7.5})
        self.assertEqual(response.status_code, 400)
        self.assertIn('6.5', str(response.data['ielts_score']))

    def test_ielts_band_rounding_follows_the_official_rule(self):
        from .exam_scores import ielts_overall
        cases = {(6.5, 6.5, 5, 7): '6.5', (6.5, 6.5, 6, 6): '6.5', (7, 7, 7, 6.5): '7.0', (6, 6, 6, 6.5): '6.0', (4, 3.5, 4, 4): '4.0'}
        for sections, expected in cases.items():
            self.assertEqual(ielts_overall(list(sections)), __import__('decimal').Decimal(expected), sections)

    def test_ielts_rejects_quarter_bands_partial_sections_and_bad_dates(self):
        cases = [
            ({'ielts_listening': 6.3}, 'ielts_listening'),
            ({'ielts_score': 10}, 'ielts_score'),
            ({'ielts_speaking': None}, 'ielts_speaking'),
            ({'ielts_test_date': None}, 'ielts_test_date'),
            ({'ielts_test_date': '2099-01-01'}, 'ielts_test_date'),
            ({'ielts_attempts': 0}, 'ielts_attempts'),
            ({'ielts_attempts': 21}, 'ielts_attempts'),
        ]
        for values, field in cases:
            response = self.post(**{**self.ielts, **values})
            self.assertEqual(response.status_code, 400, values)
            self.assertIn(field, response.data, values)

    def test_ielts_overall_only_is_still_accepted(self):
        values = {**self.ielts, 'ielts_listening': None, 'ielts_reading': None, 'ielts_writing': None, 'ielts_speaking': None, 'ielts_attempts': None}
        response = self.post(**values)
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((str(self.profile.ielts_score), self.profile.ielts_attempts), ('6.5', 1))

    def test_booked_ielts_needs_a_date_and_drops_scores(self):
        self.assertIn('ielts_test_date', self.post(ielts_status='scheduled').data)
        response = self.post(**{**self.ielts, 'ielts_status': 'scheduled', 'ielts_test_date': '2027-01-20'})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.ielts_score, self.profile.ielts_listening, str(self.profile.ielts_test_date)), (None, None, '2027-01-20'))
        self.post(ielts_status='not_taken', ielts_test_date='2027-01-20')
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.ielts_test_date)

    def test_sat_total_is_computed_from_sections(self):
        response = self.post(**self.sat, sat_superscore=True, sat_superscore_reading=800, sat_superscore_math=800)
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        # One test day: nothing to superscore, so the answer is dropped.
        self.assertEqual((self.profile.sat_score, self.profile.sat_attempts, self.profile.sat_superscore), (1350, 1, None))
        self.assertIsNone(self.profile.sat_superscore_math)

    def test_sat_validation(self):
        cases = [
            ({'sat_reading': 655}, 'sat_reading'),
            ({'sat_math': 810}, 'sat_math'),
            ({'sat_math': None}, 'sat_math'),
            ({'sat_test_date': None}, 'sat_test_date'),
            ({'sat_attempts': 2}, 'sat_superscore'),
            ({'sat_attempts': 2, 'sat_superscore': True}, 'sat_superscore_reading'),
            ({'sat_attempts': 2, 'sat_superscore': True, 'sat_superscore_reading': 640, 'sat_superscore_math': 700}, 'sat_superscore_reading'),
        ]
        for values, field in cases:
            response = self.post(**{**self.sat, **values})
            self.assertEqual(response.status_code, 400, values)
            self.assertIn(field, response.data, values)

    def test_sat_superscore_becomes_the_sent_total(self):
        response = self.post(**{**self.sat, 'sat_attempts': 3, 'sat_superscore': True, 'sat_superscore_reading': 690, 'sat_superscore_math': 720})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.sat_score, self.profile.sat_reading, self.profile.sat_superscore_reading), (1410, 650, 690))
        response = self.post(**{**self.sat, 'sat_attempts': 3, 'sat_superscore': False, 'sat_superscore_reading': 690, 'sat_superscore_math': 720})
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.sat_score, self.profile.sat_superscore, self.profile.sat_superscore_math), (1350, False, None))

    def test_ap_and_ib_score_ranges(self):
        for row, ok in [({'type': 'AP', 'subject': 'Biology', 'score': 5}, True), ({'type': 'AP', 'subject': 'Biology', 'score': 6}, False),
                        ({'type': 'IB', 'subject': 'Physics HL', 'score': 7}, True), ({'type': 'IB', 'subject': 'Physics HL', 'score': 8}, False),
                        ({'type': 'IB', 'subject': '', 'score': 4}, False)]:
            response = self.post(subjects=[row])
            self.assertEqual(response.status_code == 200, ok, (row, response.data))

    def test_headline_edit_elsewhere_drops_stale_sections(self):
        self.post(**self.ielts, **{**self.sat, 'sat_attempts': 2, 'sat_superscore': False})
        response = self.client.patch(f'/api/students/{self.profile.id}/', {'sat_score': 1500, 'ielts_score': '6.5'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.sat_score, self.profile.sat_reading, self.profile.sat_superscore), (1500, None, None))
        self.assertEqual(str(self.profile.ielts_listening), '7.0')  # still adds up to 6.5
        self.profile.ielts_score = 8
        self.profile.save(update_fields=['ielts_score'])
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.ielts_listening)

    def test_clearing_a_headline_score_resets_that_test(self):
        self.post(**self.ielts, **{**self.sat, 'sat_attempts': 2, 'sat_superscore': False})
        response = self.client.patch(f'/api/students/{self.profile.id}/', {'ielts_score': None, 'sat_score': None},
                                     format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        for name in (*IELTS_FIELDS, *SAT_FIELDS):
            expected = 'not_taken' if name.endswith('_status') else None
            self.assertEqual(getattr(self.profile, name), expected, name)

    def test_headline_scores_edited_on_their_own_follow_the_onboarding_rules(self):
        url = f'/api/students/{self.profile.id}/'
        for body, field, message in [
            ({'ielts_score': 9.5}, 'ielts_score', 'IELTS bands go from 0 to 9.'),
            ({'ielts_score': '6.3'}, 'ielts_score', 'Use whole or half bands, like 6 or 6.5.'),
            ({'ielts_score': -1}, 'ielts_score', 'IELTS bands go from 0 to 9.'),
            ({'sat_score': 1700}, 'sat_score', 'SAT totals go from 400 to 1600.'),
            ({'sat_score': 1355}, 'sat_score', 'SAT scores go up in steps of 10, like 650 or 660.'),
        ]:
            response = self.client.patch(url, body, format='json')
            self.assertEqual(response.status_code, 400, (body, response.data))
            self.assertEqual(response.data[field], [message])
        response = self.client.patch(url, {'ielts_score': '8.5', 'sat_score': 1600}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_detail_fields_are_not_writable_through_the_profile_endpoint(self):
        response = self.client.patch(f'/api/students/{self.profile.id}/', {'ielts_listening': 9, 'sat_superscore': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.ielts_listening, self.profile.sat_superscore), (None, None))

    def test_counselor_and_school_views_show_the_detail(self):
        self.post(**self.ielts, **{**self.sat, 'sat_attempts': 2, 'sat_superscore': True, 'sat_superscore_reading': 700, 'sat_superscore_math': 710})
        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/students/{self.profile.id}/').data
        self.assertEqual((detail['ielts_speaking'], detail['sat_reading'], detail['sat_superscore'], detail['sat_score']), ('6.5', 650, True, 1410))
        organization = User.objects.create_user(username='onboarding-org', email='onboarding-org@example.com', role='organization', school=self.school)
        self.client.force_authenticate(organization)
        student = self.client.get(f'/api/students/{self.profile.id}/data-visibility/').data['student']
        self.assertEqual((student['ielts_writing'], student['sat_attempts'], student['sat_superscore_math']), ('6.0', 2, 710))


class TestScoreMigrationTests(TransactionTestCase):
    migrate_from = [('admissions', '0048_safety_student_deactivated_at')]
    migrate_to = [('admissions', '0050_center_test_score_constraints')]

    def test_scores_move_from_json_into_columns(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldSchool = old_apps.get_model('admissions', 'School')
        OldUser = old_apps.get_model('users', 'User')
        OldProfile = old_apps.get_model('admissions', 'StudentProfile')
        school = OldSchool.objects.create(name='Legacy test school', code='legacy-test-school')
        make = lambda name, **values: OldProfile.objects.create(
            user=OldUser.objects.create(username=name, email=f'{name}@example.com', role='student', school=school), school=school, **values)
        taken = make('legacy-taken', ielts_score=7, sat_score=1350, application_profile={
            'ielts_status': 'taken', 'sat_status': 'taken', 'sat_reading': 650, 'sat_math': 700, 'sat_attempts': 0, 'interests': ['Arts']})
        planned = make('legacy-planned', application_profile={'ielts_status': 'scheduled', 'sat_status': 'planning'})
        broken = make('legacy-broken', ielts_score=12)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        taken, planned, broken = (StudentProfile.objects.get(pk=p.pk) for p in (taken, planned, broken))
        self.assertEqual((taken.ielts_status, taken.ielts_attempts, taken.sat_status, taken.sat_reading, taken.sat_math, taken.sat_attempts),
                         ('taken', 1, 'taken', 650, 700, 1))
        self.assertEqual(taken.application_profile, {'interests': ['Arts']})
        self.assertEqual((planned.ielts_status, planned.sat_status), ('scheduled', 'planning'))
        self.assertEqual((broken.ielts_score, broken.ielts_status), (None, 'not_taken'))


class TestScoreBackfillQueryTests(TestCase):
    def test_backfill_reads_every_field_it_writes_in_one_query(self):
        from django.apps import apps

        backfill = importlib.import_module('apps.admissions.migrations.0049_center_test_scores').move_scores_out_of_json
        school = School.objects.create(name='Backfill school', code='backfill-school')
        for index in range(3):
            user = User.objects.create(username=f'backfill-{index}', email=f'backfill-{index}@example.com',
                                       role='student', school=school)
            StudentProfile.objects.create(user=user, school=school, sat_score=1350, application_profile={
                'sat_reading': 650, 'sat_math': 700, 'sat_attempts': 2})
        with CaptureQueriesContext(connection) as queries:
            backfill(apps, None)
        # One read and one bulk update (plus its savepoint), whatever the row count.
        self.assertLessEqual(len(queries), 4, [query['sql'] for query in queries])
        self.assertEqual(set(StudentProfile.objects.values_list('sat_reading', 'sat_math', 'sat_attempts')),
                         {(650, 700, 2)})
