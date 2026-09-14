from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.admissions.models import University, UniversityProgram


class LoadUniversityCatalogTests(TestCase):
    def test_command_loads_verified_us_and_canada_catalog_idempotently(self):
        output = StringIO()
        call_command('load_university_catalog', stdout=output)

        self.assertEqual(University.objects.count(), 16)
        self.assertEqual(UniversityProgram.objects.count(), 32)
        self.assertEqual(
            set(University.objects.values_list('market', flat=True)),
            {University.Market.US, University.Market.CANADA},
        )
        self.assertFalse(University.objects.filter(catalog_source_url='').exists())
        self.assertFalse(UniversityProgram.objects.filter(source_url='').exists())
        self.assertFalse(UniversityProgram.objects.filter(verified_at__isnull=True).exists())
        self.assertIn('Loaded 16 universities and 32 programs.', output.getvalue())

        call_command('load_university_catalog', stdout=StringIO())
        self.assertEqual(University.objects.count(), 16)
        self.assertEqual(UniversityProgram.objects.count(), 32)
