"""University search ignores accents, reads Cyrillic and knows every spelling of a country."""
import importlib
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.apps import apps as django_apps
from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.admissions.models import University
from apps.admissions.search_text import MAX_VARIANTS, fold, search_variants, university_search_text
from apps.admissions.test_audit_base import AuditBaseMixin


class FoldingTests(APITestCase):
    def test_terms_and_rows_fold_alike(self):
        self.assertEqual(fold('São Paulo'), 'sao paulo')
        self.assertEqual(fold('İstanbul Teknik Üniversitesi'), 'istanbul teknik universitesi')
        self.assertEqual(fold('O‘zbekiston'), 'ozbekiston')
        self.assertIn('harvard', search_variants('Гарвард'))
        self.assertIn('columbia', search_variants('Колумбия'))
        self.assertIn('oxford', search_variants('Оксфорд'))
        self.assertEqual(search_variants('Sao'), ['sao'])

    def test_an_early_ambiguous_letter_gets_its_alternatives_under_the_cap(self):
        # Eight ambiguous letters: 384 spellings, past the cap. Г -> h must still be tried.
        variants = search_variants('гвкйхцюя')
        self.assertLessEqual(len(variants), MAX_VARIANTS + 1)
        self.assertEqual(variants[1], 'gvkykhtsyuya')
        self.assertIn('hvkykhtsyuya', variants)
        self.assertIn('gvkykhtsyua', variants)

    def test_search_text_lists_every_spelling_of_the_country(self):
        text = university_search_text('Koç University', 'İstanbul', 'Türkiye').split('\n')
        self.assertEqual(text[:2], ['koc university', 'istanbul'])
        self.assertTrue({'turkey', 'turkiye'} <= set(text))
        self.assertTrue({'us', 'usa', 'united states'} <= set(university_search_text('MIT', '', 'United States').split('\n')))

    def test_save_and_partial_save_keep_search_text(self):
        university = University.objects.create(name='Universidade de São Paulo', country='Brazil', city='São Paulo')
        self.assertIn('universidade de sao paulo', university.search_text)
        university.city = 'Ribeirão Preto'
        university.save(update_fields=['city'])
        university.refresh_from_db()
        self.assertIn('ribeirao preto', university.search_text)

    def test_the_migration_fills_existing_rows(self):
        University.objects.bulk_create([University(name='Koç University', country='Türkiye')])
        University.objects.filter(name='Koç University').update(search_text='')
        migration = importlib.import_module('apps.admissions.migrations.0070_university_search_text')
        migration.fill_search_text(django_apps, None)
        self.assertIn('koc university', University.objects.get(name='Koç University').search_text)


class IntlCostMigrationTests(APITestCase):
    def test_the_migration_fills_the_international_cost_of_the_qs_rows(self):
        call_command('load_qs_rankings', stdout=StringIO())
        mit = University.objects.get(name='Massachusetts Institute of Technology', market=University.Market.US)
        self.assertIsNone(mit.intl_cost_usd)
        # A curated value stays; an empty city is filled and searchable.
        harvard = University.objects.get(name='Harvard University', market=University.Market.US)
        University.objects.filter(pk=harvard.pk).update(intl_cost_usd=90000, city='')
        migration = importlib.import_module('apps.admissions.migrations.0071_fill_intl_cost')
        migration.fill_intl_cost(django_apps, None)
        mit.refresh_from_db()
        harvard.refresh_from_db()
        self.assertEqual(mit.intl_cost_usd, 85960)
        self.assertEqual((harvard.intl_cost_usd, harvard.city), (90000, 'Cambridge, MA'))
        self.assertIn('cambridge, ma', harvard.search_text)
        # Running it again changes nothing.
        migration.fill_intl_cost(django_apps, None)
        mit.refresh_from_db()
        self.assertEqual(mit.intl_cost_usd, 85960)


class SearchEndpointTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        make = University.objects.create
        self.usp = make(name='Universidade de São Paulo', country='Brazil', city='São Paulo')
        self.harvard = make(name='Harvard University', country='United States', city='Cambridge')
        self.ohio = make(name='Ohio State University', country='USA', city='Columbus')
        self.koc = make(name='Koç University', country='Türkiye', city='İstanbul')
        self.bilkent = make(name='Bilkent University', country='Turkey', city='Ankara')
        self.oxford = make(name='University of Oxford', country='United Kingdom', city='Oxford')
        self.client.force_authenticate(self.student_user)

    def found(self, term):
        names = {}
        for url in ('/api/college-search/?page_size=100&search=', '/api/universities/?page_size=100&search='):
            response = self.client.get(url + term)
            self.assertEqual(response.status_code, 200, response.data)
            names[url] = {row['name'] for row in response.data['results']}
        self.assertEqual(*names.values())
        return next(iter(names.values()))

    def test_accents_do_not_matter(self):
        self.assertEqual(self.found('Sao Paulo'), {self.usp.name})
        self.assertEqual(self.found('São'), {self.usp.name})
        self.assertEqual(self.found('koc'), {self.koc.name})
        self.assertEqual(self.found('Istanbul'), {self.koc.name})

    def test_cyrillic_is_transliterated(self):
        self.assertEqual(self.found('Гарвард'), {self.harvard.name})
        self.assertEqual(self.found('Оксфорд'), {self.oxford.name})

    def test_country_spellings_find_one_country(self):
        united_states = {self.harvard.name, self.ohio.name}
        self.assertEqual(self.found('USA'), united_states)
        self.assertEqual(self.found('United States'), united_states)
        self.assertTrue(united_states <= self.found('US'))
        turkey = {self.koc.name, self.bilkent.name}
        for spelling in ('Turkey', 'Türkiye', 'Turkiye'):
            self.assertEqual(self.found(spelling), turkey, spelling)

    def test_the_detail_does_not_expose_search_text(self):
        self.assertNotIn('search_text', self.client.get(f'/api/universities/{self.koc.id}/').data)

    def test_a_city_filled_by_the_scorecard_load_is_searchable_unaccented(self):
        university = University.objects.create(name='Example Polytechnic University', country='United States')
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder) / 'scorecard.json'
            snapshot.write_text(json.dumps({'source': 'College Scorecard', 'universities': [
                {'name': university.name, 'city': 'Mayagüez, PR'},
            ]}), encoding='utf-8')
            call_command('load_college_scorecard', file=str(snapshot), stdout=StringIO())
        university.refresh_from_db()
        self.assertEqual(university.city, 'Mayagüez, PR')
        self.assertEqual(self.found('Mayaguez'), {university.name})
