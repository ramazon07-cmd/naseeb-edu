"""Admission chance: entry gates, the academic gate, the band grid and the frozen snapshot."""
from rest_framework.test import APITestCase

from apps.admissions import admission_chance
from apps.admissions.admission_chance import chance, international_rate
from apps.admissions.models import AdmissionChanceSnapshot, Application, University
from apps.admissions.test_college_fit import FitFixture, stub_university


def context(**values):
    return {
        'gpa': 3.8, 'gpa_scale': 4, 'sat': None, 'sat_status': 'not_taken', 'act': None,
        'english': {'test': 'IELTS', 'score': 7.0, 'ielts': 7.0}, 'countries': ['us'], 'major': '',
        'major_name': '', 'scholarship_needed': False, 'strength': 6, **values,
    }


def band(context_values=None, **university):
    return chance(stub_university(**university), context(**(context_values or {})))['band']


class InternationalRateTests(APITestCase):
    def test_a_published_international_rate_wins(self):
        self.assertEqual(international_rate(stub_university(acceptance_rate=4, intl_acceptance_rate=2.1)), (2.1, False))

    def test_selective_rates_are_estimated_lower_for_students_from_abroad(self):
        self.assertEqual(international_rate(stub_university(acceptance_rate=10)), (5.0, True))
        self.assertEqual(international_rate(stub_university(acceptance_rate=40)), (32.0, True))
        self.assertEqual(international_rate(stub_university(acceptance_rate=60)), (60.0, False))
        self.assertEqual(international_rate(stub_university()), (None, False))


class BandGridTests(APITestCase):
    def test_safety_needs_an_open_admit_rate_and_a_strong_position(self):
        strong = {'sat': 1450}
        self.assertEqual(band(strong, acceptance_rate=60, sat_min=1200, sat_max=1400), 'safety')
        self.assertEqual(band({'sat': 1300, 'strength': 0}, acceptance_rate=60, sat_min=1200, sat_max=1400), 'target')
        # 40% overall is 32% for students from abroad: target at best.
        self.assertEqual(band(strong, acceptance_rate=40, sat_min=1200, sat_max=1400), 'target')

    def test_under_five_percent_is_a_far_reach_for_everyone(self):
        perfect = {'sat': 1600, 'gpa': 4.0, 'strength': 10}
        self.assertEqual(band(perfect, acceptance_rate=4, sat_min=1500, sat_max=1570), 'far_reach')
        # Even without a score to compare.
        self.assertEqual(band({}, acceptance_rate=4, sat_min=1500, sat_max=1570), 'far_reach')

    def test_no_admit_rate_means_no_band(self):
        self.assertIsNone(band({'sat': 1500}, sat_min=1200, sat_max=1400))

    def test_rows_and_positions_are_monotonic(self):
        # A stronger position never gives a harder band, and a lower rate never an easier one.
        order = admission_chance.STEPS
        for _, row in admission_chance.GRID:
            ranks = [order.index(row[name]) for name in ('very_low', 'low', 'mid', 'strong')]
            self.assertEqual(ranks, sorted(ranks))
        for name in ('very_low', 'low', 'mid', 'strong'):
            ranks = [order.index(row[name]) for _, row in admission_chance.GRID]
            self.assertEqual(ranks, sorted(ranks, reverse=True))


class AcademicGateTests(APITestCase):
    def test_strong_activities_cannot_lift_weak_academics(self):
        university = dict(acceptance_rate=60, sat_min=1300, sat_max=1400, market='us')
        weak = {'sat': 1150, 'gpa': 2.8, 'strength': 10}
        result = chance(stub_university(**university), context(**weak))
        self.assertLess(result['academic_position'], -1)
        self.assertEqual(result['band'], 'reach')
        self.assertIn('academics_below_bar', [note['code'] for note in result['notes']])

    def test_activities_count_once_academics_reach_the_bar(self):
        university = dict(acceptance_rate=30, sat_min=1300, sat_max=1400)
        at_bar = {'sat': 1360, 'gpa': 3.9}
        busy = chance(stub_university(**university), context(strength=10, **at_bar))
        idle = chance(stub_university(**university), context(strength=0, **at_bar))
        self.assertGreater(busy['position'], idle['position'])

    def test_academics_far_below_the_range_are_a_far_reach(self):
        self.assertEqual(band({'sat': 900, 'gpa': 2.0}, acceptance_rate=70, sat_min=1300, sat_max=1400), 'far_reach')


class GateTests(APITestCase):
    def test_a_credential_route_makes_the_school_not_eligible_with_the_route(self):
        for route, code in (
            ('foundation', 'credential_foundation'), ('one_year_uni', 'credential_one_year'),
            ('studienkolleg', 'credential_studienkolleg'), ('not_accepted', 'credential_not_accepted'),
        ):
            result = chance(stub_university(acceptance_rate=70, credential_route=route), context())
            self.assertEqual(result['band'], 'not_eligible', route)
            self.assertEqual([gap['code'] for gap in result['gates']], [code])
        self.assertEqual(band(acceptance_rate=70, credential_route='direct'), 'safety')

    def test_english_below_the_minimum_is_not_eligible(self):
        english = {'english': {'test': 'TOEFL', 'score': 80, 'ielts': 6.5}}
        result = chance(stub_university(acceptance_rate=70, ielts_min=7.0), context(**english))
        self.assertEqual(result['band'], 'not_eligible')
        self.assertEqual(result['gates'][0]['params'], {'test': 'TOEFL', 'score': 80, 'min': 7.0})
        self.assertEqual(band(english, acceptance_rate=70, ielts_min=6.5), 'safety')
        # No English score yet: the gate cannot be checked, so it does not fail.
        self.assertEqual(band({'english': None}, acceptance_rate=70, ielts_min=7.0), 'safety')

    def test_need_aware_moves_aid_seekers_one_band_harder(self):
        university = dict(acceptance_rate=70, intl_need_policy='need_aware')
        self.assertEqual(band({'scholarship_needed': False}, **university), 'safety')
        self.assertEqual(band({'scholarship_needed': True}, **university), 'target')

    def test_an_entrance_exam_caps_the_band_at_target(self):
        result = chance(stub_university(acceptance_rate=80, entrance_exam='Mathematics test'), context())
        self.assertEqual(result['band'], 'target')
        self.assertEqual(result['notes'][0]['params'], {'exam': 'Mathematics test'})


class SnapshotTests(FitFixture, APITestCase):
    def add(self, university):
        response = self.client.post('/api/applications/', {
            'student': self.student.id, 'university': university.id, 'program': 'Computer Science', 'tier': 'target',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return Application.objects.get(pk=response.data['id'])

    def test_adding_a_university_freezes_what_college_search_said(self):
        self.ready_profile()
        fit = self.fit(self.state)
        application = self.add(self.state)
        snapshot = application.chance_snapshot
        self.assertEqual(
            (snapshot.band, snapshot.fit_score, snapshot.position, snapshot.admission_model, snapshot.algorithm_version),
            (fit['admission_band'], fit['match_score'], fit['chance']['position'], 'academic_plus_us', admission_chance.ALGORITHM_VERSION),
        )
        self.assertEqual(snapshot.inputs['sat'], 1450)
        # Frozen: a later profile change does not rewrite it.
        self.ready_profile(sat_score=1100)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.inputs['sat'], 1450)

    def test_failed_gates_are_kept_with_the_snapshot(self):
        self.ready_profile()
        University.objects.filter(pk=self.oxford.pk).update(credential_route='foundation', acceptance_rate='17.00')
        snapshot = self.add(self.oxford).chance_snapshot
        self.assertEqual((snapshot.band, snapshot.gates), ('not_eligible', ['credential_foundation']))

    def test_no_snapshot_while_the_research_profile_is_incomplete(self):
        self.add(self.state)
        self.assertFalse(AdmissionChanceSnapshot.objects.exists())


class LoadRequirementsTests(APITestCase):
    def test_the_shipped_requirements_load_onto_catalogue_rows_and_rerun_cleanly(self):
        from io import StringIO

        from django.core.management import call_command

        cardiff = University.objects.create(name='Cardiff University', country='United Kingdom', acceptance_rate='75.00')
        lse = University.objects.create(name='London School of Economics and Political Science', country='United Kingdom')
        out = StringIO()
        call_command('load_admission_requirements', stdout=out)
        cardiff.refresh_from_db()
        lse.refresh_from_db()
        self.assertEqual((cardiff.credential_route, lse.credential_route), ('foundation', 'not_accepted'))
        self.assertTrue(cardiff.requirements_source_url.startswith('https://www.cardiff.ac.uk/'))
        self.assertIn('Not in the catalogue, skipped: Khalifa University', out.getvalue())
        rerun = StringIO()
        call_command('load_admission_requirements', stdout=rerun)
        self.assertIn('Updated 0 universities', rerun.getvalue())
