"""Catalog deployment and repeat-import regression coverage."""
from importlib import import_module

from django.apps import apps
from django.db import connection
from django.test import TestCase
from types import SimpleNamespace

from .models import OpportunityProgram, StoreItem
from .serializers import OpportunityProgramSerializer, StoreItemSerializer

migration = import_module('apps.admissions.migrations.0035_portal_catalog')


class PortalCatalogTests(TestCase):
    """The migration already ran for the test database; these assert it stays safe to re-run."""

    def load(self):
        migration.load_catalog(apps, SimpleNamespace(connection=connection))

    def test_snapshot_is_loaded_with_grades_ages_and_source_links(self):
        program = OpportunityProgram.objects.get(source_key='sheet-immerse-education-essay-competition')
        self.assertEqual(program.eligible_grades, '6,7,8,9,10,11')
        self.assertEqual(program.eligible_ages, '13-18')
        self.assertEqual(str(program.deadline), '2026-10-25')
        self.assertTrue(program.application_url.startswith('https://'))
        self.assertGreater(OpportunityProgram.objects.filter(source_key__startswith='sheet-').count(), 90)

    def test_undated_entries_keep_the_spreadsheet_deadline_text_and_are_served(self):
        program = OpportunityProgram.objects.get(source_key='sheet-tks')
        self.assertIsNone(program.deadline)
        self.assertEqual(program.deadline_text, '30.04')
        self.assertTrue(program.needs_verification)
        data = OpportunityProgramSerializer(program).data
        self.assertEqual(data['deadline_text'], '30.04')
        self.assertEqual(data['eligible_grades'], '6,7,8,9,10,11')

    def test_import_is_repeatable_and_preserves_edits(self):
        before = OpportunityProgram.objects.count()
        program = OpportunityProgram.objects.get(source_key='sheet-tks')
        program.description = 'Administrator reviewed this record'
        program.save()
        service = StoreItem.objects.get(catalog_key='sample-essay-review')
        service.price_amount = 700000
        service.provider_name = 'Real provider'
        service.is_sample = False
        service.save()

        self.load()

        program.refresh_from_db()
        service.refresh_from_db()
        self.assertEqual(OpportunityProgram.objects.count(), before)
        self.assertEqual(program.description, 'Administrator reviewed this record')
        self.assertEqual(service.price_amount, 700000)
        self.assertEqual(service.provider_name, 'Real provider')
        self.assertFalse(service.is_sample)

    def test_hand_curated_record_is_never_duplicated_by_the_import(self):
        OpportunityProgram.objects.filter(source_key='sheet-tks').delete()
        OpportunityProgram.objects.create(title='TKS', provider='Naseeb', category='Research',
                                          program_type=OpportunityProgram.ProgramType.INTERNATIONAL,
                                          description='Curated by the counselor team')
        self.load()
        rows = OpportunityProgram.objects.filter(title='TKS')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().description, 'Curated by the counselor team')

    def test_sample_service_api_exposes_price_provider_and_sample_flag(self):
        data = StoreItemSerializer(StoreItem.objects.get(catalog_key='sample-essay-review')).data
        self.assertTrue(data['is_sample'])
        self.assertEqual(data['currency'], 'USD')
        self.assertEqual(len(data['deliverables']), 3)
