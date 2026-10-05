"""College Scorecard import: admissions facts for the catalogue's US universities."""
import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from .management.commands.load_college_scorecard import DATA_FILE
from .models import University

MIT = {
    'name': 'Massachusetts Institute of Technology (MIT)', 'unitid': 166683, 'acceptance_rate': 4.55,
    'sat_min': 1520, 'sat_max': 1580, 'act_min': 34, 'act_max': 36, 'test_optional': False, 'cost_usd': 82730,
    'tuition_usd': 62396, 'undergrad_enrollment': 4535, 'city': 'Cambridge, MA', 'website': 'https://web.mit.edu/',
    'campus_setting': 'urban',
}


class LoadCollegeScorecardTests(TestCase):
    def load(self, *rows):
        output = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder) / 'scorecard.json'
            snapshot.write_text(json.dumps({'source': 'College Scorecard', 'source_url': 'https://collegescorecard.ed.gov/data/', 'universities': list(rows)}), encoding='utf-8')
            call_command('load_college_scorecard', file=str(snapshot), stdout=output)
        return output.getvalue()

    def test_fills_a_qs_named_university_under_its_curated_name(self):
        mit = University.objects.create(name='Massachusetts Institute of Technology', country='United States')
        self.load(MIT)
        mit.refresh_from_db()
        self.assertEqual(
            (mit.acceptance_rate, mit.sat_min, mit.sat_max, mit.act_min, mit.net_price_usd, mit.tuition_usd, mit.undergrad_enrollment),
            (Decimal('4.55'), 1520, 1580, 34, 82730, 62396, 4535),
        )
        self.assertEqual((mit.city, mit.website, mit.campus_setting, mit.test_optional), ('Cambridge, MA', 'https://web.mit.edu/', 'urban', False))

    def test_curated_values_stay_and_only_blanks_are_filled(self):
        duke = University.objects.create(name='Duke University', country='USA', sat_min=1490, sat_max=1570, city='Durham, NC')
        self.load({'name': 'Duke University', 'sat_min': 1500, 'sat_max': 1560, 'acceptance_rate': 5.1, 'cost_usd': 90000, 'city': 'Elsewhere, NC', 'test_optional': True})
        duke.refresh_from_db()
        self.assertEqual((duke.sat_min, duke.sat_max, duke.city), (1490, 1570, 'Durham, NC'))
        self.assertEqual((duke.acceptance_rate, duke.net_price_usd, duke.test_optional), (Decimal('5.10'), 90000, True))

    def test_running_again_changes_nothing(self):
        University.objects.create(name='Massachusetts Institute of Technology', country='United States')
        self.load(MIT)
        self.assertIn('Filled 0 universities', self.load(MIT))

    def test_rows_without_a_catalogue_university_are_reported(self):
        output = self.load(MIT)
        self.assertIn('Filled 0 universities', output)
        self.assertIn('1 are not in the catalogue yet: run load_qs_rankings first.', output)

    def test_shipped_snapshots_fill_the_qs_us_universities(self):
        rows = json.loads(DATA_FILE.read_text(encoding='utf-8'))['universities']
        call_command('load_qs_rankings', stdout=StringIO())
        output = StringIO()
        call_command('load_college_scorecard', stdout=output)
        self.assertIn(f'Filled {len(rows)} universities', output.getvalue())
        self.assertNotIn('not in the catalogue', output.getvalue())
        # load_qs_rankings gave MIT its curated spelling; the Scorecard row still finds it.
        mit = University.objects.get(name='Massachusetts Institute of Technology')
        self.assertEqual((mit.acceptance_rate, mit.net_price_usd), (Decimal('4.55'), 82730))
        self.assertGreaterEqual(University.objects.filter(market=University.Market.US, acceptance_rate__isnull=False).count(), 180)
