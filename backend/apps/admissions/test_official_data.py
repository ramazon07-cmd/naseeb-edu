"""import_official_aid, import_official_programs and the college match's use of official aid numbers."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.admissions import aid_fx
from apps.admissions.college_match import aid_facts, aid_status, budget_position, gives_international_aid
from apps.admissions.models import OpportunityProgram, University
from apps.admissions.test_college_match import URL, MatchFixture


def write(rows):
    handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(rows, handle)
    handle.close()
    return handle.name


def run(command, *paths, **options):
    out = StringIO()
    call_command(command, *paths, stdout=out, **options)
    return out.getvalue()


def aid_row(name, country, **values):
    return {
        'name': name, 'country': country, 'official_domain': None, 'intl_aid_available': 'unknown',
        'intl_need_policy': 'unknown', 'need_based_for_intl': None, 'merit_for_intl': None, 'meets_full_need_intl': None,
        'full_ride_available': None, 'currency': 'unknown', 'cost_of_attendance': None, 'cost_includes_living': None,
        'tuition_intl': None, 'max_award': None, 'typical_award': None, 'min_student_pays': None,
        'academic_year': None, 'aid_url': None, 'notes': None, 'sources': [], 'verified_at': '2026-11-23', **values,
    }


class ImportOfficialAidTests(APITestCase):
    def setUp(self):
        self.uni = University.objects.create(name='Example University', country='United Kingdom', average_aid_usd=4000, financial_aid_url='https://old.example/aid')
        self.other = University.objects.create(name='Other College', country='Germany')

    def row(self, **values):
        return aid_row('Example University', 'United Kingdom', **values)

    def test_merit_and_need_answers_also_set_the_flags_college_search_filters_on(self):
        run('import_official_aid', write([self.row(merit_for_intl=True, need_based_for_intl=True)]))
        self.uni.refresh_from_db()
        self.assertTrue(self.uni.offers_merit_aid and self.uni.offers_need_based_aid)

    def test_a_no_never_clears_the_college_search_flags(self):
        University.objects.filter(pk=self.uni.pk).update(offers_merit_aid=True, offers_need_based_aid=True)
        run('import_official_aid', write([self.row(merit_for_intl=False, need_based_for_intl=False)]))
        self.uni.refresh_from_db()
        self.assertTrue(self.uni.offers_merit_aid and self.uni.offers_need_based_aid)
        self.assertFalse(self.uni.intl_merit_based or self.uni.intl_need_based)

    def test_rates_are_fixed_and_unlisted_currencies_are_not_guessed(self):
        self.assertEqual(aid_fx.to_usd(1000, 'GBP'), 1270)
        self.assertEqual(aid_fx.to_usd(1000, 'USD'), 1000)
        self.assertIsNone(aid_fx.to_usd(1000, 'XXX'))
        self.assertIsNone(aid_fx.to_usd(None, 'GBP'))

    def test_a_row_is_saved_and_converted_to_usd(self):
        path = write([self.row(
            intl_aid_available='limited', intl_need_policy='need_aware', merit_for_intl=True, need_based_for_intl=False,
            official_domain='example.ac.uk', currency='GBP', max_award=10000, typical_award=5000, min_student_pays=20000, academic_year='2026-27',
            aid_url='https://example.ac.uk/aid', notes='Merit awards up to 10,000 GBP.', sources=['https://example.ac.uk/aid', 'not a url'],
        )])
        output = run('import_official_aid', path)
        self.assertIn('1 rows: 1 updated', output)
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_aid_availability, 'limited')
        self.assertTrue(self.uni.offers_international_aid)
        self.assertEqual(self.uni.intl_need_policy, 'need_aware')
        self.assertTrue(self.uni.intl_merit_based)
        self.assertIs(self.uni.intl_need_based, False)
        self.assertEqual((self.uni.intl_max_award, self.uni.intl_min_student_pays), (10000, 20000))
        self.assertEqual((self.uni.intl_max_award_usd, self.uni.intl_typical_award_usd, self.uni.intl_min_student_pays_usd), (12700, 6350, 25400))
        self.assertEqual(self.uni.average_aid_usd, 6350)
        self.assertEqual(str(self.uni.aid_fx_rate), '1.270000')
        self.assertEqual(self.uni.financial_aid_url, 'https://example.ac.uk/aid')
        self.assertEqual(self.uni.aid_sources, ['https://example.ac.uk/aid'])
        self.assertEqual(str(self.uni.aid_verified_at), '2026-11-23')

    def test_a_different_spelling_matches_when_only_one_university_fits(self):
        mit = University.objects.create(name='Massachusetts Institute of Technology', country='USA')
        path = write([aid_row('Massachusetts Institute of Technology (MIT)', 'United States', intl_aid_available='yes')])
        output = run('import_official_aid', path)
        self.assertIn('0 unmatched', output)
        mit.refresh_from_db()
        self.assertEqual(mit.intl_aid_availability, 'yes')

    def test_a_loose_match_never_lands_on_a_university_named_exactly_by_another_row(self):
        path = write([self.row(intl_aid_available='yes'), aid_row('Example University (EU)', 'United Kingdom', intl_aid_available='no')])
        output = run('import_official_aid', path)
        self.assertIn('1 unmatched', output)
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_aid_availability, 'yes')

    def test_running_twice_changes_nothing(self):
        path = write([self.row(intl_aid_available='yes', currency='USD', max_award=30000, min_student_pays=0)])
        run('import_official_aid', path)
        self.uni.refresh_from_db()
        before = (self.uni.updated_at, self.uni.intl_min_student_pays_usd)
        self.assertEqual(before[1], 0)
        self.assertIn('0 updated, 1 unchanged', run('import_official_aid', path))
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.updated_at, before[0])

    def test_nulls_and_unknown_never_overwrite_known_values(self):
        run('import_official_aid', write([self.row(intl_aid_available='yes', currency='USD', max_award=30000, min_student_pays=5000, notes='Official note', aid_url='https://a.edu/aid')]))
        run('import_official_aid', write([self.row()]))
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_aid_availability, 'yes')
        self.assertEqual((self.uni.intl_max_award_usd, self.uni.intl_min_student_pays_usd), (30000, 5000))
        self.assertEqual(self.uni.aid_application_notes, 'Official note')
        self.assertEqual(self.uni.financial_aid_url, 'https://a.edu/aid')

    def test_an_unlisted_currency_leaves_usd_empty_and_is_reported(self):
        output = run('import_official_aid', write([self.row(intl_aid_available='yes', currency='XXX', max_award=5000)]))
        self.assertIn('1 in a currency without a rate', output)
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_max_award, 5000)
        self.assertIsNone(self.uni.intl_max_award_usd)

    def test_unmatched_rows_are_reported_and_never_create_universities(self):
        count = University.objects.count()
        output = run('import_official_aid', write([aid_row('No Such College', 'Spain', intl_aid_available='yes')]))
        self.assertIn('1 unmatched', output)
        self.assertIn('UNMATCHED: No Such College (Spain)', output)
        self.assertEqual(University.objects.count(), count)

    def test_matching_ignores_case_and_several_files_load(self):
        first = write([aid_row('example university', 'united kingdom', intl_aid_available='no')])
        second = write([aid_row('Other College', 'Germany', intl_aid_available='yes')])
        self.assertIn('2 rows: 2 updated', run('import_official_aid', first, second))
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_aid_availability, 'no')
        self.assertFalse(self.uni.offers_international_aid)

    def test_only_sources_on_the_official_domain_are_kept(self):
        row = self.row(official_domain='example.ac.uk', intl_aid_available='yes', sources=[
            'https://example.ac.uk/aid', 'https://study.example.ac.uk/fees', 'https://notexample.ac.uk/x', 'https://aggregator.com/example.ac.uk',
        ])
        run('import_official_aid', write([row]))
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.aid_sources, ['https://example.ac.uk/aid', 'https://study.example.ac.uk/fees'])

    def test_unlisted_currencies_and_volatile_ones_are_not_converted(self):
        for code in ('unknown', 'ARS', 'VES'):
            self.assertIsNone(aid_fx.to_usd(100, code))
        for code in ('COP', 'MOP', 'OMR', 'BAM', 'UAH', 'PAB'):
            self.assertIsNotNone(aid_fx.to_usd(100000, code), code)

    def test_without_a_path_the_shipped_research_files_load(self):
        from apps.admissions.management.commands.import_official_aid import DEFAULT_FILES
        self.assertEqual(len(DEFAULT_FILES), 8)
        output = run('import_official_aid', dry_run=True)
        self.assertIn('1504 rows', output)

    def test_dry_run_writes_nothing(self):
        output = run('import_official_aid', write([self.row(intl_aid_available='yes')]), dry_run=True)
        self.assertIn('[dry run]', output)
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.intl_aid_availability, '')

    def test_the_shipped_sample_shape_loads(self):
        sample = Path('/Users/macbook/code/naseeb-edu-research/data/research/financial_aid/universities_1.json')
        if not sample.exists():
            self.skipTest('research sample not present')
        University.objects.create(name='Massachusetts Institute of Technology (MIT)', country='United States')
        self.assertIn('1 updated', run('import_official_aid', str(sample)))


class ImportOfficialProgramsTests(APITestCase):
    def setUp(self):
        self.program = OpportunityProgram.objects.create(
            title='Old title', provider='opportunitiescorners.com', program_type='international', category='Summer program',
            needs_verification=True, source_url='https://opportunitiescorners.com/x', description='',
        )

    def row(self, **values):
        return {
            'id': self.program.pk, 'title': 'Summer Fellows', 'provider': 'Stanford University', 'official_url': 'https://cddrl.example.edu/summerfellows',
            'application_url': 'https://cddrl.example.edu/apply', 'description': 'A three-week residential fellowship.',
            'program_type': 'international', 'category': 'Fellowship', 'delivery_mode': 'onsite', 'country': 'United States', 'city': 'Stanford',
            'eligible_grades': None, 'eligible_ages': 'Ages 25+', 'open_to_international': True, 'open_to_uzbekistan': None,
            'next_deadline': '2027-01-12', 'deadline_text': '2027 program: January 12.', 'start_date': '2027-07-18', 'end_date': '2027-08-06',
            'fee_usd': None, 'fee_text': None, 'scholarship_available': True, 'aid_details': 'Limited travel aid.',
            'requirements': 'Two references', 'still_running': True, 'sources': ['https://cddrl.example.edu/summerfellows'], 'verified_at': '2026-11-23',
            **values,
        }

    def test_fields_are_updated_and_the_row_is_marked_verified(self):
        output = run('import_official_programs', write([self.row()]))
        self.assertIn('1 rows: 1 updated', output)
        self.program.refresh_from_db()
        self.assertEqual(self.program.description, 'A three-week residential fellowship.')
        self.assertEqual(self.program.application_url, 'https://cddrl.example.edu/apply')
        self.assertEqual(self.program.source_url, 'https://cddrl.example.edu/summerfellows')
        self.assertEqual(str(self.program.deadline), '2027-01-12')
        self.assertEqual((self.program.country, self.program.city, self.program.eligible_ages), ('United States', 'Stanford', 'Ages 25+'))
        self.assertIs(self.program.open_to_international, True)
        self.assertIsNone(self.program.open_to_uzbekistan)
        self.assertFalse(self.program.needs_verification)
        self.assertTrue(self.program.is_active)
        self.assertEqual(self.program.official_sources, ['https://cddrl.example.edu/summerfellows'])

    def test_prose_grades_become_codes_and_the_prose_is_kept_in_requirements(self):
        self.program.eligible_grades = 'Grades 9\u201312'  # what the last import wrote
        self.program.save()
        path = write([self.row(eligible_grades='Grades 9\u201312')])
        run('import_official_programs', path)
        self.program.refresh_from_db()
        self.assertEqual(self.program.eligible_grades, '9,10,11')
        self.assertEqual(self.program.requirements, 'Eligible grades: Grades 9\u201312\nTwo references')
        self.assertIn('0 updated, 1 unchanged', run('import_official_programs', path))

    def test_grade_prose_is_parsed_into_the_codes_readers_expect(self):
        from apps.admissions.management.commands.import_official_programs import grade_codes
        for prose, codes in (
            ('Grades 9\u201312', '9,10,11'), ('Grades 9-12', '9,10,11'), ('High school', '9,10,11'),
            ('Grade 11; entering Grade 12 in fall 2027', '11'), ('Completed high school', 'gap'),
            ('Grades 5\u20138', '5,6,7,8'), ('Rising Grades 10\u201312', '10,11'), ('Grade 12', '11'),
            ('Grades 3-7', '5,6,7'), ('Grade 2', ''), ('Current high school students; graduates ineligible', '9,10,11'), ('Gap year or high school graduates', 'gap'),
            ('Students in grades 9, 10 and 11', '9,10,11'), ('University students', ''), ('', ''), (None, ''),
        ):
            with self.subTest(prose=prose):
                self.assertEqual(grade_codes(prose), codes)

    def test_unparseable_grade_text_leaves_the_stored_value_alone(self):
        self.program.eligible_grades = '9,10'
        self.program.save()
        run('import_official_programs', write([self.row(eligible_grades='Undergraduates only')]))
        self.program.refresh_from_db()
        self.assertEqual(self.program.eligible_grades, '9,10')

    def test_running_twice_changes_nothing(self):
        path = write([self.row()])
        run('import_official_programs', path)
        self.program.refresh_from_db()
        stamp = self.program.updated_at
        self.assertIn('0 updated, 1 unchanged', run('import_official_programs', path))
        self.program.refresh_from_db()
        self.assertEqual(self.program.updated_at, stamp)

    def test_nulls_never_overwrite_and_unknown_is_not_no(self):
        self.program.fee_usd = 500
        self.program.deadline_text = 'Rolling'
        self.program.save()
        run('import_official_programs', write([self.row(fee_usd=None, deadline_text=None, next_deadline=None, open_to_international=None, scholarship_available=None)]))
        self.program.refresh_from_db()
        self.assertEqual((self.program.fee_usd, self.program.deadline_text), (500, 'Rolling'))
        self.assertIsNone(self.program.open_to_international)

    def test_a_program_that_ended_is_deactivated_and_a_running_one_is_not_reactivated_by_null(self):
        run('import_official_programs', write([self.row(still_running=False)]))
        self.program.refresh_from_db()
        self.assertFalse(self.program.is_active)
        run('import_official_programs', write([self.row(still_running=None)]))
        self.program.refresh_from_db()
        self.assertFalse(self.program.is_active)

    def test_existing_title_and_provider_are_kept_and_aggregator_sources_dropped(self):
        run('import_official_programs', write([self.row(
            title='Official Name', provider='Official Org', application_url='https://forms.gle/abc',
            sources=['https://opportunitiescorners.com/x', 'https://docs.google.com/spreadsheets/1', 'https://cddrl.example.edu/summerfellows'],
        )]))
        self.program.refresh_from_db()
        self.assertEqual((self.program.title, self.program.provider), ('Old title', 'opportunitiescorners.com'))
        self.assertEqual(self.program.official_sources, ['https://cddrl.example.edu/summerfellows'])
        self.assertEqual(self.program.application_url, '')

    def test_without_a_path_the_shipped_research_file_loads(self):
        self.assertIn('rows', run('import_official_programs', dry_run=True))

    def test_placeholders_and_unknown_ids_are_skipped_and_a_row_without_official_data_keeps_needs_verification(self):
        before = OpportunityProgram.objects.count()
        output = run('import_official_programs', write([
            {'id': self.program.pk, 'placeholder': True}, {'id': 99999, 'title': 'Ghost'},
            {'id': self.program.pk, 'official_url': None, 'application_url': None, 'sources': [], 'still_running': None},
        ]))
        self.assertIn('1 placeholders skipped', output)
        self.assertIn('1 ids not found', output)
        self.assertIn('1 without official data', output)
        self.assertEqual(OpportunityProgram.objects.count(), before)
        self.program.refresh_from_db()
        self.assertTrue(self.program.needs_verification)

    def test_the_serializer_exposes_the_new_fields_to_the_program_page(self):
        run('import_official_programs', write([self.row()]))
        from apps.admissions.serializers import OpportunityProgramSerializer
        body = OpportunityProgramSerializer(OpportunityProgram.objects.get(pk=self.program.pk)).data
        for name in ('open_to_international', 'fee_text', 'official_sources', 'official_verified_at', 'source_url', 'description'):
            self.assertIn(name, body)


class ImportProgramDetailsTests(APITestCase):
    def setUp(self):
        self.program = OpportunityProgram.objects.create(title='The Earth Prize', provider='The Earth Prize', program_type='international', category='Competition')

    def detail(self, **values):
        return {
            'id': self.program.pk, 'overview': 'A global sustainability competition for teams of up to 5.', 'team': 'Teams of up to 5',
            'benefits': ['7 regional winning teams get $10,000 each', '', None, '1:1 mentoring'], 'who_can_apply': ['Ages 13-19'],
            'requirements': ['A sustainability project'], 'selection_process': 'Regional judging, then a final.', 'country': 'Switzerland', 'age_range': '13-19',
            'past_participants_uz': [], **values,
        }

    def load(self, *rows):
        return run('import_official_programs', write([{'id': self.program.pk, 'official_url': None}]), details=write(list(rows)))

    def test_details_are_stored_cleaned_and_a_second_run_changes_nothing(self):
        self.load(self.detail())
        self.program.refresh_from_db()
        self.assertEqual(self.program.benefits, ['7 regional winning teams get $10,000 each', '1:1 mentoring'])
        self.assertEqual((self.program.team_format, self.program.country, self.program.eligible_ages), ('Teams of up to 5', 'Switzerland', '13-19'))
        self.assertEqual((self.program.who_can_apply, self.program.requirements_list), (['Ages 13-19'], ['A sustainability project']))
        self.assertIn('1 unchanged', self.load(self.detail()))

    def test_null_or_empty_details_never_overwrite_and_existing_country_is_kept(self):
        OpportunityProgram.objects.filter(pk=self.program.pk).update(country='Germany', benefits=['Old benefit'])
        self.load(self.detail(benefits=[], overview=None, country='Switzerland'))
        self.program.refresh_from_db()
        self.assertEqual((self.program.country, self.program.benefits), ('Germany', ['Old benefit']))

    def test_past_participants_need_a_name_and_a_source_and_linkedin_must_be_a_profile(self):
        good = {'name': 'Aziz Karimov', 'role': 'winner', 'year': 2024, 'linkedin_url': 'https://www.linkedin.com/in/aziz-karimov/', 'source_url': 'https://example.org/winners'}
        self.load(self.detail(past_participants_uz=[
            good,
            {'name': 'Search Only', 'role': 'participant', 'year': 2023, 'linkedin_url': 'https://www.linkedin.com/search/results/people/?keywords=x', 'source_url': 'https://example.org/p'},
            {'name': 'No Source', 'role': 'winner', 'year': 2023, 'linkedin_url': None, 'source_url': None},
            {'name': 'Aziz Karimov', 'source_url': 'https://example.org/dup'},
            {'role': 'winner', 'source_url': 'https://example.org/x'},
            *[{'name': f'Person {n}', 'source_url': 'https://example.org/p'} for n in range(8)],
        ]))
        self.program.refresh_from_db()
        people = self.program.past_participants
        self.assertEqual(len(people), 5)
        self.assertEqual(people[0], good)
        self.assertIsNone(people[1]['linkedin_url'])
        self.assertNotIn('No Source', [person['name'] for person in people])

    def test_a_named_program_file_skips_the_shipped_details(self):
        run('import_official_programs', write([{'id': self.program.pk, 'official_url': None}]))
        self.program.refresh_from_db()
        self.assertEqual(self.program.benefits, [])

    def test_the_shipped_details_file_is_well_formed(self):
        from apps.admissions.management.commands.import_official_programs import DETAILS_FILE
        from apps.admissions.program_details import LIST_LIMITS, clean_people
        rows = json.loads(DETAILS_FILE.read_text(encoding='utf-8'))
        self.assertTrue(rows)
        for row in rows:
            people = row.get('past_participants_uz') or []
            self.assertEqual(len(clean_people(people) or []), len(people), f'a person of row {row["id"]} would be dropped')
            self.assertLessEqual(len(people), 5)
            # Nothing is cut to fit: every list in the file is within the stored limit.
            for field, name in (('benefits', 'benefits'), ('who_can_apply', 'who_can_apply'), ('requirements', 'requirements_list')):
                self.assertLessEqual(len(row.get(field) or []), LIST_LIMITS[name], (row['id'], field))

    def test_long_requirement_lists_keep_every_item_up_to_the_limit(self):
        items = [f'Requirement number {n}' for n in range(12)]
        self.load(self.detail(requirements=items))
        self.program.refresh_from_db()
        self.assertEqual(self.program.requirements_list, items)

    def test_a_newer_edition_replaces_the_older_place_dates_and_sources(self):
        OpportunityProgram.objects.filter(pk=self.program.pk).update(
            country='United States', city='Washington DC', start_date='2025-04-03', end_date='2025-04-05', deadline_text='2025 deadline', deadline='2025-01-01',
        )
        self.load(self.detail(edition_core={
            'country': 'Switzerland', 'city': 'Geneva', 'start_date': '2027-02-10', 'end_date': None, 'deadline': '2026-12-01',
            'deadline_text': 'Apply by December 1, 2026', 'sources': ['https://www.theearthprize.org/2027', 'https://forms.gle/x'],
        }))
        self.program.refresh_from_db()
        self.assertEqual((self.program.country, self.program.city), ('Switzerland', 'Geneva'))
        self.assertEqual((str(self.program.start_date), self.program.end_date, str(self.program.deadline)), ('2027-02-10', None, '2026-12-01'))
        self.assertEqual((self.program.deadline_text, self.program.official_sources), ('Apply by December 1, 2026', ['https://www.theearthprize.org/2027']))
        self.assertIn('1 unchanged', self.load(self.detail(edition_core={
            'country': 'Switzerland', 'city': 'Geneva', 'start_date': '2027-02-10', 'end_date': None, 'deadline': '2026-12-01',
            'deadline_text': 'Apply by December 1, 2026', 'sources': ['https://www.theearthprize.org/2027'],
        })))

    def test_the_serializer_exposes_the_detail_fields(self):
        from apps.admissions.serializers import OpportunityProgramSerializer
        body = OpportunityProgramSerializer(self.program).data
        for name in ('overview', 'benefits', 'who_can_apply', 'requirements_list', 'team_format', 'selection_process', 'past_participants'):
            self.assertIn(name, body)


class OfficialAidMatchTests(MatchFixture, APITestCase):
    def match(self):
        response = self.client.post(URL)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def cards(self, data):
        return {row['name']: row for group in data['groups'] for row in group['results']}

    def test_availability_reads_yes_limited_no_and_unknown_stays_unknown(self):
        uni = University(name='A', country='Canada')
        self.assertEqual(aid_status(uni), 'unknown')
        self.assertEqual(aid_facts(uni)['availability'], 'unknown')
        uni.intl_aid_availability = 'limited'
        self.assertEqual(aid_status(uni), 'limited')
        self.assertTrue(gives_international_aid(uni))
        uni.intl_aid_availability = 'no'
        self.assertEqual(aid_status(uni), 'none')
        self.assertFalse(gives_international_aid(uni))
        uni.intl_aid_availability = 'unknown'
        self.assertEqual(aid_status(uni), 'unknown')

    def test_budget_position_uses_the_minimum_after_aid(self):
        self.assertEqual(budget_position(60000, 20000, 15000), 'within_with_aid')
        self.assertEqual(budget_position(60000, 20000, 25000), 'over')
        self.assertEqual(budget_position(60000, 20000, None), 'over')
        self.assertEqual(budget_position(10000, 20000, 15000), 'within')

    def test_a_card_carries_official_aid_facts_and_a_budget_reason(self):
        self.ready_profile(budget_usd=20000)
        University.objects.filter(pk=self.mit.pk).update(
            intl_aid_availability='yes', intl_max_award_usd=85000, intl_min_student_pays_usd=0,
            financial_aid_url='https://sfs.mit.edu/aid', aid_academic_year='2026-27',
        )
        card = self.cards(self.match())[self.mit.name]
        self.assertEqual(card['aid_status'], 'yes')
        self.assertEqual(card['cost_vs_budget'], 'within_with_aid')
        self.assertEqual(card['aid']['max_award_usd'], 85000)
        self.assertEqual(card['aid']['min_student_pays_usd'], 0)
        self.assertEqual(card['aid']['source_url'], 'https://sfs.mit.edu/aid')
        self.assertEqual(card['fit']['reasons'][0]['code'], 'aid_fits_budget')
        # Without researched data the card says unknown and shows no numbers.
        other = self.cards(self.match())[self.state.name]
        self.assertEqual(other['aid']['availability'], 'unknown')
        self.assertIsNone(other['aid']['min_student_pays_usd'])
        self.assertNotIn('aid_fits_budget', [item['code'] for item in other['fit']['reasons']])

    def test_a_student_needing_a_scholarship_does_not_see_a_university_still_above_budget_after_aid(self):
        self.ready_profile(budget_usd=20000, scholarship_needed=True)
        University.objects.filter(pk=self.mit.pk).update(intl_aid_availability='limited', intl_min_student_pays_usd=60000)
        data = self.match()
        self.assertNotIn(self.mit.name, self.cards(data))
        self.assertIn('over_budget_with_aid', [note['code'] for note in data['notes']])

    def test_unknown_minimum_keeps_the_university_and_over_budget_is_shown_for_others(self):
        self.ready_profile(budget_usd=20000, scholarship_needed=False)
        University.objects.filter(pk=self.mit.pk).update(intl_aid_availability='limited', intl_min_student_pays_usd=60000)
        card = self.cards(self.match())[self.mit.name]
        self.assertEqual(card['cost_vs_budget'], 'over')
        self.assertEqual(card['fit']['gaps'][0]['code'], 'aid_over_budget')

    def test_an_official_no_drops_a_university_for_a_student_needing_aid(self):
        self.ready_profile(budget_usd=10000, scholarship_needed=True)
        University.objects.filter(pk=self.state.pk).update(intl_aid_availability='no', offers_international_aid=False)
        self.assertNotIn(self.state.name, self.cards(self.match()))
