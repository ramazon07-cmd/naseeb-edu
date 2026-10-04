"""Other test scores and certificates (TOEFL, Duolingo, PTE, ACT, Cambridge, other) in the Test scores section.

They are stored like the AP / IB rows, as StudentProfile.application_profile['certificates'], and are written
only through POST / PATCH /api/students/onboarding/. (The Documents page's certificates are uploaded files and
have nothing to do with these rows.)
"""
import datetime

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users import api_messages
from apps.users.models import User
from .models import ParentStudentLink, School, StudentProfile
from .onboarding import CERTIFICATE_RULES, MAX_CERTIFICATES, OnboardingSerializer, current_answers
from .section_review import SECTION_FIELDS, Section

URL = '/api/students/onboarding/'
KEY = 'certificates'
SECRET = 'Zeta Language Certificate'
SENT = [
    {'type': 'toefl', 'score': 105, 'test_date': '2026-03-14'},
    {'type': 'duolingo', 'score': 125},
    {'type': 'pte', 'score': 79},
    {'type': 'act', 'score': 34},
    {'type': 'cambridge', 'score': '190', 'name': 'a name is dropped for a standard test'},
    {'type': 'other', 'name': SECRET, 'score': 'Level B2', 'test_date': '2026-04-02'},
]
STORED = [
    {'type': 'toefl', 'name': '', 'score': 105, 'test_date': '2026-03-14'},
    {'type': 'duolingo', 'name': '', 'score': 125, 'test_date': None},
    {'type': 'pte', 'name': '', 'score': 79, 'test_date': None},
    {'type': 'act', 'name': '', 'score': 34, 'test_date': None},
    {'type': 'cambridge', 'name': '', 'score': 190, 'test_date': None},
    {'type': 'other', 'name': SECRET, 'score': 'Level B2', 'test_date': '2026-04-02'},
]


class CertificateBase(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters are keyed by user id, and ids repeat between tests
        self.school = School.objects.create(name='Certificate school', code='certificate-test')
        self.counselor = self.make_user('counselor', User.Role.COUNSELOR)
        self.student = self.make_user('student', User.Role.STUDENT)
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school, assigned_counselor=self.counselor)
        self.payload = dict(
            first_name='Aziza', last_name='Karimova', gender='Female', grade='11', graduation_year=2027,
            school_name='Certificate school', country='Uzbekistan', city='Tashkent', gpa_scale='5', gpa=4.6,
            ielts_status='not_taken', sat_status='not_taken', target_countries='US', interests=['Science'],
            honors=[], activities=[],
        )
        self.client.force_authenticate(self.student)
        response = self.client.post(URL, self.payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def make_user(self, name, role, school=True):
        """A user of this school; pass school=None for accounts that have none (parent, product admin)."""
        return User.objects.create_user(
            username=f'cert-{name}', email=f'cert-{name}@example.com', role=role,
            school=self.school if school is True else school,
        )

    def stored(self, profile=None):
        profile = profile or self.profile
        profile.refresh_from_db()
        return profile.application_profile.get(KEY)

    def patch(self, rows, **extra):
        return self.client.patch(URL, {KEY: rows}, format='json', **extra)

    def post(self, rows, **extra):
        return self.client.post(URL, {**self.payload, KEY: rows}, format='json', **extra)

    def assert_row_errors(self, rows, expected):
        """Both a section edit (PATCH) and a full POST answer 400 with these per-row errors, and store nothing."""
        before = self.stored()
        for send in (self.patch, self.post):
            response = send(rows)
            self.assertEqual(response.status_code, 400, (send.__name__, rows, response.data))
            self.assertEqual(response.data[KEY], expected, (send.__name__, rows))
        self.assertEqual(self.stored(), before)


class CertificateStorageTests(CertificateBase):
    def test_onboarding_stores_every_type_and_reads_it_back(self):
        response = self.post(SENT)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored(), STORED)
        self.assertEqual(response.data['profile']['application_profile'][KEY], STORED)
        self.assertEqual(self.client.get(URL).data['application_profile'][KEY], STORED)
        self.assertEqual(self.client.get(f'/api/students/{self.profile.pk}/').data['application_profile'][KEY], STORED)
        # A standard test is stored as a number, free text as text.
        rows = self.stored()
        self.assertTrue(all(type(row['score']) is int for row in rows[:5]), rows)
        self.assertIsInstance(rows[5]['score'], str)

    def test_section_edit_replaces_clears_and_leaves_every_other_answer(self):
        before = dict(self.profile.application_profile)
        response = self.patch(SENT)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored(), STORED)
        self.assertEqual(response.data['profile']['application_profile'][KEY], STORED)
        for key, value in before.items():
            self.assertEqual(self.profile.application_profile[key], value, key)

        response = self.patch([{'type': 'act', 'score': 30}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored(), [{'type': 'act', 'name': '', 'score': 30, 'test_date': None}], 'the list is replaced, not merged')

        self.assertEqual(self.client.patch(URL, {'city': 'Samarkand'}, format='json').status_code, 200)
        self.assertEqual(len(self.stored()), 1, 'editing another answer leaves the rows alone')

        self.assertEqual(self.patch([]).status_code, 200)
        self.assertEqual(self.stored(), [])

    def test_retakes_are_kept_in_the_order_given(self):
        rows = [
            {'type': 'toefl', 'score': 88, 'test_date': '2025-05-01'},
            {'type': 'act', 'score': 30},
            {'type': 'toefl', 'score': 101, 'test_date': '2026-02-01'},
        ]
        self.assertEqual(self.patch(rows).status_code, 200)
        self.assertEqual([(row['type'], row['score']) for row in self.stored()], [('toefl', 88), ('act', 30), ('toefl', 101)])

    def test_a_sat_or_ielts_only_edit_does_not_wipe_the_rows(self):
        self.assertEqual(self.patch(SENT).status_code, 200)
        sat = dict(sat_status='taken', sat_reading=650, sat_math=700, sat_test_date='2026-05-02', sat_attempts=1)
        ielts = dict(ielts_status='taken', ielts_score=7, ielts_test_date='2026-03-14', ielts_attempts=1)
        for label, answers in (('SAT', sat), ('IELTS', ielts), ('SAT cleared', {'sat_status': 'not_taken'})):
            with self.subTest(edit=label):
                response = self.client.patch(URL, answers, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.stored(), STORED)
                self.assertEqual(response.data['profile']['application_profile'][KEY], STORED)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.ielts_score, self.profile.sat_status), (7, 'not_taken'))

    def test_saving_the_whole_tests_section_keeps_the_rows_it_carries(self):
        # What the Student Center sends for the section: every test answer, the rows in the shape the API returns them.
        section = dict(
            sat_status='taken', sat_reading=650, sat_math=700, sat_test_date='2026-05-02', sat_attempts=1,
            ielts_status='not_taken', subjects=[{'type': 'AP', 'subject': 'Biology', 'score': 5}], **{KEY: STORED},
        )
        response = self.client.patch(URL, section, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stored(), STORED)
        self.assertEqual(self.profile.application_profile['subjects'], [{'type': 'AP', 'subject': 'Biology', 'score': 5}])
        self.assertEqual(self.profile.sat_score, 1350)
        # The same section saved again with the rows left out keeps them: only a sent list is replaced.
        del section[KEY]
        self.assertEqual(self.client.patch(URL, section, format='json').status_code, 200)
        self.assertEqual(self.stored(), STORED)

    def test_profiles_saved_before_certificates_existed_still_work(self):
        legacy = {'interests': ['Arts'], 'subjects': [{'type': 'AP', 'subject': 'Biology', 'score': 5}]}
        StudentProfile.objects.filter(pk=self.profile.pk).update(application_profile=legacy)
        self.profile.refresh_from_db()
        self.assertEqual(current_answers(self.profile)[KEY], [], 'an absent list is read as an empty one')

        self.client.force_authenticate(self.counselor)
        detail = self.client.get(f'/api/students/{self.profile.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['application_profile'], legacy)

        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.patch(URL, {'city': 'Bukhara'}, format='json').status_code, 200)
        self.assertEqual(self.patch(STORED[:1]).status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.application_profile['subjects'], legacy['subjects'])
        self.assertEqual(self.profile.application_profile['interests'], ['Arts'])
        self.assertEqual(self.stored(), STORED[:1])

    def test_a_full_list_costs_no_extra_queries(self):
        self.patch([{'type': 'act', 'score': 20}])
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self.patch([{'type': 'act', 'score': 21}]).status_code, 200)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.patch([{'type': 'act', 'score': 22}] * MAX_CERTIFICATES).status_code, 200)
        self.assertEqual(len(many), len(one), [query['sql'] for query in many])


class CertificateValidationTests(CertificateBase):
    def test_each_type_accepts_its_limits_and_rejects_beyond_them(self):
        for kind, rule in CERTIFICATE_RULES.items():
            self.assertIn(str(rule.low), rule.out_of_range, kind)
            self.assertIn(str(rule.high), rule.out_of_range, kind)
            for score in (rule.low, rule.high):
                with self.subTest(kind=kind, accepted=score):
                    response = self.patch([{'type': kind, 'score': score}])
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertEqual(self.stored()[0]['score'], score)
            for score in (rule.low - rule.step, rule.high + rule.step):
                with self.subTest(kind=kind, rejected=score):
                    self.assert_row_errors([{'type': kind, 'score': score}], [{'score': [rule.out_of_range]}])

    def test_duolingo_goes_up_in_steps_of_five(self):
        for score in (10, 15, 125, 160):
            self.assertEqual(self.patch([{'type': 'duolingo', 'score': score}]).status_code, 200, score)
        step = CERTIFICATE_RULES['duolingo'].off_step
        for score in (11, 123, 159):
            with self.subTest(score=score):
                self.assert_row_errors([{'type': 'duolingo', 'score': score}], [{'score': [step]}])
        # The other tests count in ones.
        for kind in ('toefl', 'pte', 'act', 'cambridge'):
            self.assertEqual(self.patch([{'type': kind, 'score': CERTIFICATE_RULES[kind].low + 1}]).status_code, 200, kind)

    def test_a_standard_score_is_a_whole_number_sent_as_a_number_or_numeric_text(self):
        for sent in (90, '90', ' 90 ', '090'):
            with self.subTest(sent=sent):
                self.assertEqual(self.patch([{'type': 'toefl', 'score': sent}]).status_code, 200)
                self.assertEqual(self.stored()[0]['score'], 90)
        whole = 'Enter a whole number.'
        for sent in (90.5, 90.0, '90.5', 'ninety', '9e1', '1_0', '٩٠', '+90', '--9'):
            with self.subTest(sent=sent):
                self.assert_row_errors([{'type': 'toefl', 'score': sent}], [{'score': [whole]}])
        self.assert_row_errors([{'type': 'toefl', 'score': True}], [{'score': ['Not a valid string.']}])
        self.assert_row_errors([{'type': 'toefl', 'score': None}], [{'score': ['This field may not be null.']}])
        for blank in ('', '   '):
            self.assert_row_errors([{'type': 'toefl', 'score': blank}], [{'score': ['Enter your score or result.']}])

    def test_other_needs_a_name_and_keeps_free_text(self):
        name_needed = [{'name': ['Enter the name of the certificate.']}]
        for name in ('', '   ', None):
            with self.subTest(name=name):
                self.assert_row_errors([{'type': 'other', 'name': name, 'score': 'Level B2'}], name_needed)
        self.assert_row_errors([{'type': 'other', 'score': 'Level B2'}], name_needed)

        longest = {'type': 'other', 'name': 'N' * 120, 'score': 'S' * 40}
        self.assertEqual(self.patch([longest]).status_code, 200)
        self.assertEqual(self.stored()[0]['name'], 'N' * 120)
        self.assert_row_errors([{**longest, 'name': 'N' * 121}], [{'name': ['Ensure this field has no more than 120 characters.']}])
        self.assert_row_errors([{**longest, 'score': 'S' * 41}], [{'score': ['Ensure this field has no more than 40 characters.']}])

        # Free text is not parsed: a numeric-looking result of an "other" certificate stays a string.
        self.assertEqual(self.patch([{'type': 'other', 'name': 'Olympiad', 'score': '105'}]).status_code, 200)
        self.assertEqual(self.stored()[0]['score'], '105')
        self.assertEqual(self.patch([{'type': 'other', 'name': '  Olympiad  ', 'score': ' Gold medal '}]).status_code, 200)
        self.assertEqual((self.stored()[0]['name'], self.stored()[0]['score']), ('Olympiad', 'Gold medal'))

    def test_a_standard_test_never_keeps_a_name(self):
        self.assertEqual(self.patch([{'type': 'toefl', 'name': 'something', 'score': 90}]).status_code, 200)
        self.assertEqual(self.stored()[0]['name'], '')
        self.assertEqual(self.patch([{'type': 'toefl', 'name': None, 'score': 90}]).status_code, 200)

    def test_a_row_is_always_complete_and_of_a_known_type(self):
        # A PATCH is partial for the whole payload; DRF then skips a row's missing fields instead of reporting them.
        required = 'This field is required.'
        self.assert_row_errors([{}], [{'type': [required], 'score': [required]}])
        self.assert_row_errors([{'type': 'toefl'}], [{'score': [required]}])
        self.assert_row_errors([{'score': 90}], [{'type': [required]}])
        unknown = 'Choose the type of test or certificate.'
        for kind in ('sat', 'ielts', 'TOEFL', 'AP', '', None):
            with self.subTest(kind=kind):
                self.assertEqual(self.patch([{'type': kind, 'score': 90}]).status_code, 400)
        self.assert_row_errors([{'type': 'sat', 'score': 1400}], [{'type': [unknown]}])
        self.assert_row_errors([{'type': 'TOEFL', 'score': 90}], [{'type': [unknown]}])

    def test_test_date_rules_match_the_sat_and_ielts_dates(self):
        today = timezone.localdate()
        for value in (None, today.isoformat(), '2015-01-01'):
            with self.subTest(accepted=value):
                response = self.patch([{'type': 'act', 'score': 30, 'test_date': value}])
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.stored()[0]['test_date'], value)
        self.assertEqual(self.patch([{'type': 'act', 'score': 30}]).status_code, 200)
        self.assertIsNone(self.stored()[0]['test_date'], 'the date is optional')

        tomorrow = (today + datetime.timedelta(days=1)).isoformat()
        self.assert_row_errors([{'type': 'act', 'score': 30, 'test_date': tomorrow}], [{'test_date': ['The test date cannot be in the future.']}])
        self.assert_row_errors([{'type': 'act', 'score': 30, 'test_date': '2099-01-01'}], [{'test_date': ['The test date cannot be in the future.']}])
        self.assert_row_errors([{'type': 'act', 'score': 30, 'test_date': '2014-12-31'}], [{'test_date': ['Enter a date from 2015 or later.']}])
        response = self.patch([{'type': 'act', 'score': 30, 'test_date': 'last spring'}])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data[KEY][0]['test_date'][0].startswith('Date has wrong format'))

    def test_at_most_thirty_rows(self):
        full = [{'type': 'act', 'score': 30}] * MAX_CERTIFICATES
        self.assertEqual(self.patch(full).status_code, 200)
        self.assertEqual(len(self.stored()), 30)
        too_many = 'You can add up to 30 other test scores or certificates.'
        self.assertEqual(MAX_CERTIFICATES, 30)
        for send in (self.patch, self.post):
            response = send([*full, {'type': 'act', 'score': 31}])
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data[KEY], {'non_field_errors': [too_many]})
        self.assertEqual(len(self.stored()), 30, 'a rejected list changes nothing')

    def test_errors_come_back_as_a_list_with_one_entry_per_row(self):
        response = self.patch([{'type': 'toefl', 'score': 90}, {'type': 'toefl', 'score': 121}, {'type': 'zzz', 'score': 1}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data[KEY], [
            {},
            {'score': ['TOEFL iBT scores go from 0 to 120.']},
            {'type': ['Choose the type of test or certificate.']},
        ])

    def test_the_list_itself_must_be_a_list(self):
        for value in ('toefl', {'type': 'toefl', 'score': 90}, 90):
            with self.subTest(value=value):
                response = self.client.patch(URL, {KEY: value}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn(KEY, response.data)


class CertificateLocalizationTests(CertificateBase):
    def test_row_errors_come_back_in_the_request_language(self):
        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        rows = [
            {'type': 'toefl', 'score': 121},
            {'type': 'duolingo', 'score': 12},
            {'type': 'pte', 'score': 5},
            {'type': 'act', 'score': 37},
            {'type': 'cambridge', 'score': 79},
            {'type': 'duolingo', 'score': 5},
            {'type': 'zzz', 'score': 1},
            {'type': 'other', 'score': 'Level B2'},
            {'type': 'pte', 'score': 'abc'},
            {'type': 'act', 'score': ''},
            {'type': 'act', 'score': 30, 'test_date': tomorrow},
            {'type': 'act', 'score': 30, 'test_date': '2014-12-31'},
        ]
        english = [
            CERTIFICATE_RULES['toefl'].out_of_range, CERTIFICATE_RULES['duolingo'].off_step,
            CERTIFICATE_RULES['pte'].out_of_range, CERTIFICATE_RULES['act'].out_of_range,
            CERTIFICATE_RULES['cambridge'].out_of_range, CERTIFICATE_RULES['duolingo'].out_of_range,
            'Choose the type of test or certificate.', 'Enter the name of the certificate.', 'Enter a whole number.',
            'Enter your score or result.', 'The test date cannot be in the future.', 'Enter a date from 2015 or later.',
        ]
        for language in ('uz', 'ru'):
            with self.subTest(language=language):
                response = self.patch(rows, HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.status_code, 400)
                got = [next(iter(entry.values()))[0] for entry in response.data[KEY]]
                self.assertEqual(got, [api_messages.EXACT[message][language] for message in english])
        uz = self.patch(rows[:1], HTTP_ACCEPT_LANGUAGE='uz')
        ru = self.patch(rows[:1], HTTP_ACCEPT_LANGUAGE='ru')
        self.assertEqual(uz.data[KEY], [{'score': ['TOEFL iBT ballari 0 dan 120 gacha bo‘ladi.']}])
        self.assertEqual(ru.data[KEY], [{'score': ['Баллы TOEFL iBT — от 0 до 120.']}])

    def test_the_row_limit_message_keeps_its_number_in_every_language(self):
        rows = [{'type': 'act', 'score': 30}] * (MAX_CERTIFICATES + 1)
        english = self.patch(rows, HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(english.data[KEY]['non_field_errors'], ['You can add up to 30 other test scores or certificates.'])
        for language, text in (
            ('uz', 'Boshqa test natijalari yoki sertifikatlardan ko‘pi bilan 30 tasini qo‘shish mumkin.'),
            ('ru', 'Можно добавить не более 30 других результатов тестов или сертификатов.'),
        ):
            response = self.patch(rows, HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.data[KEY]['non_field_errors'], [text], language)


class CertificateReviewTests(CertificateBase):
    def review_tests(self, status='approved'):
        self.client.force_authenticate(self.counselor)
        response = self.client.post(f'/api/students/{self.profile.pk}/section-review/', {'section': 'tests', 'status': status}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.student)

    def reviews(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        return {section: item['status'] for section, item in response.data['profile']['section_reviews'].items()}

    def test_changing_the_rows_sends_the_tests_section_back_for_review(self):
        self.review_tests()
        self.client.force_authenticate(self.counselor)
        self.client.post(f'/api/students/{self.profile.pk}/section-review/', {'section': 'academics', 'status': 'approved'}, format='json')
        self.client.force_authenticate(self.student)
        reviews = self.reviews(self.patch(SENT))
        self.assertEqual(reviews['tests'], 'waiting')
        self.assertEqual(reviews['academics'], 'approved', 'another section keeps its review')

    def test_saving_the_same_rows_again_keeps_the_review(self):
        self.patch(SENT)
        self.review_tests()
        self.assertEqual(self.reviews(self.patch(SENT))['tests'], 'approved')
        # The same rows sent in the shape the API returns them are the same answer too.
        self.assertEqual(self.reviews(self.patch(STORED))['tests'], 'approved')

    def test_the_first_save_of_no_rows_is_not_an_edit(self):
        # Every profile saved before certificates existed has no entry; its approved tests section must survive
        # the student pressing Save without adding anything.
        self.assertNotIn(KEY, self.profile.application_profile)
        self.review_tests()
        self.assertEqual(self.reviews(self.patch([]))['tests'], 'approved')
        self.assertEqual(self.stored(), [])

    def test_removing_every_row_is_an_edit(self):
        self.patch(SENT)
        self.review_tests()
        self.assertEqual(self.reviews(self.patch([]))['tests'], 'waiting')

    def test_editing_another_section_leaves_the_tests_review_alone(self):
        self.patch(SENT)
        self.review_tests()
        response = self.client.patch(URL, {'city': 'Samarkand'}, format='json')
        self.assertEqual(self.reviews(response)['tests'], 'approved')

    def test_a_rejected_list_does_not_touch_the_review(self):
        self.review_tests()
        self.assertEqual(self.patch([{'type': 'toefl', 'score': 500}]).status_code, 400)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(URL).data['section_reviews']['tests']['status'], 'approved')

    def test_every_answer_the_form_validates_belongs_to_a_review_section(self):
        # A field outside every section would be saved but would never send its section back for review.
        # (The frontend lists the same fields per step in ONBOARDING_STEP_FIELDS.)
        in_a_section = set().union(*SECTION_FIELDS.values())
        self.assertEqual(set(OnboardingSerializer().fields) - in_a_section, set())
        self.assertEqual([section for section, fields in SECTION_FIELDS.items() if KEY in fields], [Section.TESTS])


class CertificateScopeTests(CertificateBase):
    """Who can read and write the rows: the same people as for the AP / IB rows, and nobody else."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.patch(SENT).status_code, 200)
        self.other_school = School.objects.create(name='Other certificate school', code='certificate-other')
        self.teacher = self.make_user('teacher', User.Role.TEACHER)
        self.organization = self.make_user('organization', User.Role.ORGANIZATION)
        self.admin = self.make_user('admin', User.Role.ADMIN, school=None)
        self.parent = self.make_user('parent', User.Role.PARENT, school=None)

    def listed(self, response):
        return response.data.get('results', response.data)

    def test_staff_who_may_see_the_student_read_the_rows_with_the_profile(self):
        for user in (self.counselor, self.teacher, self.organization, self.admin):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                detail = self.client.get(f'/api/students/{self.profile.pk}/')
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.data['application_profile'][KEY], STORED)
                row = next(item for item in self.listed(self.client.get('/api/students/')) if item['id'] == self.profile.pk)
                self.assertEqual(row['application_profile'][KEY], STORED)

    def test_nobody_else_can_read_the_rows(self):
        classmate = self.make_user('classmate', User.Role.STUDENT)
        StudentProfile.objects.create(user=classmate, school=self.school)
        far_student = self.make_user('far-student', User.Role.STUDENT, school=self.other_school)
        StudentProfile.objects.create(user=far_student, school=self.other_school)
        outsiders = {
            'classmate': classmate,
            'student of another school': far_student,
            'counselor who is not assigned': self.make_user('unassigned', User.Role.COUNSELOR),
            'counselor of another school': self.make_user('far-counselor', User.Role.COUNSELOR, school=self.other_school),
            'teacher of another school': self.make_user('far-teacher', User.Role.TEACHER, school=self.other_school),
            'school account of another school': self.make_user('far-organization', User.Role.ORGANIZATION, school=self.other_school),
            'parent without a link': self.parent,
        }
        for label, user in outsiders.items():
            with self.subTest(who=label):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(f'/api/students/{self.profile.pk}/').status_code, 404)
                listing = self.client.get('/api/students/')
                self.assertEqual(listing.status_code, 200)
                self.assertNotIn(SECRET, str(listing.data))
                self.assertNotIn(self.profile.pk, [item['id'] for item in self.listed(listing)])

    def test_a_linked_parent_gets_no_test_rows(self):
        ParentStudentLink.objects.create(parent=self.parent, student=self.profile, status=ParentStudentLink.Status.ACTIVE, consented_at=timezone.now())
        self.client.force_authenticate(self.parent)
        portal = self.client.get('/api/parent-portal/')
        self.assertEqual(portal.status_code, 200)
        self.assertNotIn(SECRET, str(portal.data))
        self.assertNotIn(KEY, str(portal.data))
        self.assertEqual(self.client.get(f'/api/students/{self.profile.pk}/').status_code, 404)

    def test_only_the_student_writes_rows_and_only_through_the_onboarding_endpoint(self):
        attempt = [{'type': 'toefl', 'score': 1}]
        for user in (self.counselor, self.teacher, self.organization, self.admin, self.parent):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                self.assertEqual(self.patch(attempt).status_code, 403)
                self.assertEqual(self.post(attempt).status_code, 403)
        self.assertEqual(self.stored(), STORED)

    def test_a_student_cannot_write_rows_onto_another_profile(self):
        other = self.make_user('other-student', User.Role.STUDENT, school=self.other_school)
        other_profile = StudentProfile.objects.create(user=other, school=self.other_school)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(URL, {**self.payload, 'school_name': 'Other certificate school'}, format='json').status_code, 200)
        # The endpoint always works on the caller's own profile, never on the one named in the request.
        self.assertEqual(self.client.patch(URL, {KEY: [{'type': 'act', 'score': 11}], 'user': self.student.pk, 'id': self.profile.pk}, format='json').status_code, 200)
        self.assertEqual(self.stored(other_profile), [{'type': 'act', 'name': '', 'score': 11, 'test_date': None}])
        self.assertEqual(self.stored(), STORED)
        # The profile endpoint cannot be used as a side door: the other profile is out of scope ...
        denied = self.client.patch(f'/api/students/{self.profile.pk}/', {'application_profile': {KEY: []}}, format='json')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.stored(), STORED)

    def test_a_student_cannot_write_rows_through_the_profile_endpoint(self):
        self.client.force_authenticate(self.student)
        response = self.client.patch(f'/api/students/{self.profile.pk}/', {'application_profile': {KEY: [{'type': 'toefl', 'score': 1}]}}, format='json')
        self.assertEqual(response.status_code, 200, 'read-only fields are ignored, not an error')
        self.assertEqual(self.stored(), STORED, 'rows are only written by the endpoint that validates them')

    def test_the_school_safe_student_360_does_not_carry_the_rows(self):
        # AP / IB rows are not part of this view either. Showing school and admin accounts any part of the
        # profile answers is a privacy decision (CLAUDE.md section 6), so this pins the current boundary.
        for user in (self.organization, self.admin):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                visibility = self.client.get(f'/api/students/{self.profile.pk}/data-visibility/')
                self.assertEqual(visibility.status_code, 200)
                self.assertNotIn('application_profile', visibility.data['student'])
                self.assertNotIn(SECRET, str(visibility.data))
                self.assertNotIn(KEY, str(visibility.data))
