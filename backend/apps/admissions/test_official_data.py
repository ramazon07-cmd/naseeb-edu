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

    def test_rates_are_fixed_and_unlisted_currencies_are_not_guessed(self):
        self.assertEqual(aid_fx.to_usd(1000, 'GBP'), 1270)
        self.assertEqual(aid_fx.to_usd(1000, 'USD'), 1000)
        self.assertIsNone(aid_fx.to_usd(1000, 'XXX'))
        self.assertIsNone(aid_fx.to_usd(None, 'GBP'))

    def test_a_row_is_saved_and_converted_to_usd(self):
        path = write([self.row(
            intl_aid_available='limited', intl_need_policy='need_aware', merit_for_intl=True, need_based_for_intl=False,
            currency='GBP', max_award=10000, typical_award=5000, min_student_pays=20000, academic_year='2026-27',
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
