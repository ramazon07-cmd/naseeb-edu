"""QS subject rankings: the spreadsheet converter, the loader and the major -> subject map."""
import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from .management.commands.load_qs_subject_rankings import DATA_FILE
from .models import University, UniversitySubjectRank
from .subjects import SUBJECT_WEIGHTS, SUBJECTS, split_majors, subjects_for_major

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'build_qs_subject_catalog.py'
try:
    import openpyxl
except ImportError:  # the converter is a dev-only script
    openpyxl = None


class ConverterTests(unittest.TestCase):
    def build(self, folder):
        workbook = openpyxl.Workbook()
        workbook.active.title = 'Index'
        methodology = workbook.create_sheet('methodology')
        methodology.append(['SUBJECT_ID', 'SUBJECT_CODE', 'SUBJECT_NAME', 'Academic'])
        methodology.append([5, 'ARC01', 'Archaeology', 0.7])
        methodology.append([28, 'HIS01', 'History', 0.6])
        methodology.append([91, 'F-ART', 'Arts & Humanities', 0.6])
        header = ['2026', '2025', 'INSTITUTION', 'COUNTRY/TERRITORY', 'ACADEMIC', 'ACADEMIC RANK', 'EMPLOYER', 'EMPLOYER RANK',
                  'CITATIONS', 'CITATIONS RANK', 'H', 'H RANK', 'IRN', 'IRN RANK', 'SCORE']
        # Weights (Academic, Employer, Citations, H index, IRN) as QS prints them above each table.
        weights = {'Arts & Humanities': [0.6, 0.2, 0.075, 0.075, 0.05], 'Archaeology': [0.7, 0.1, 0.1, 0.1, 0], 'History_Subject': [0.6, 0.1, 0.15, 0.15, 0]}
        sheets = {
            'Arts & Humanities': [[1, 1, 'University of Cambridge', 'United Kingdom', 100, 1, 99, 2, 80.5, 9, 90, 3, 70.1, 4, 98.4]],
            'Archaeology': [
                [1, 1, 'University of Cambridge', 'United Kingdom', 100, 1, 95, 2, 90, 3, 88.5, 4, None, None, 98.4],
                ['=51', '=60', 'Massachusetts Institute of Technology (MIT)', 'United States of America', 70, 5, 60.2, 6, 50, 7, 40, 8, None, None, 70.2],
                ['201-250', '151-200', 'Peking University', 'China (Mainland)', 60, 9, 55, 10, 45, 11, 35, 12, None, None, None],
            ],
            'History_Subject': [[3, 4, 'UCL', 'United Kingdom', 90, 1, 80, 2, 70, 3, 60, 4, None, None, 90.1]],
        }
        for name, rows in sheets.items():
            sheet = workbook.create_sheet(name)
            sheet.append(['QS by Subject', None, None, None, None, 'Academic', 'Employer', 'Citations per Paper', 'H Index', 'International Research Network'])
            sheet.append([name, None, None, None, None, *weights[name]])
            sheet.append([])
            sheet.append(header)
            for row in rows:
                sheet.append(row)
                for cell in sheet[sheet.max_row]:
                    if isinstance(cell.value, str) and cell.value.startswith('='):
                        cell.data_type = 's'  # '=51' is a published tie, not a formula
        path = Path(folder) / 'subjects.xlsx'
        workbook.save(path)
        return path

    @unittest.skipIf(openpyxl is None, 'openpyxl is a dev-only dependency of the converter')
    def test_subjects_areas_ranges_ties_and_scores_are_read(self):
        spec = importlib.util.spec_from_file_location('build_qs_subject_catalog', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            workbook = openpyxl.load_workbook(self.build(folder), read_only=True, data_only=True)
            subjects = module.subjects_of(workbook)
            self.assertEqual([(code, name, area) for code, name, area, _ in subjects], [
                ('AREA_ART', 'Arts & Humanities', 'AREA_ART'),
                ('ARC01', 'Archaeology', 'AREA_ART'),
                ('HIS01', 'History', 'AREA_ART'),
            ])
            weights = module.weights_of(workbook['Archaeology'])
            rows = list(module.sheet_rows(workbook['Archaeology'], 'ARC01', weights))
        # Only the four indicators Archaeology uses are stored (IRN has weight 0), in the sheet's order.
        self.assertEqual(weights, [0.7, 0.1, 0.1, 0.1, 0])
        self.assertEqual(rows, [
            ['ARC01', 1, '', 'University of Cambridge', 'United Kingdom', 98.4, 100.0, 95.0, 90.0, 88.5],
            ['ARC01', 51, '=51', 'Massachusetts Institute of Technology (MIT)', 'United States', 70.2, 70.0, 60.2, 50.0, 40.0],
            ['ARC01', 201, '201-250', 'Peking University', 'China', None, 60.0, 55.0, 45.0, 35.0],
        ])

    def test_the_shipped_snapshot_is_complete(self):
        snapshot = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        self.assertEqual(snapshot['year'], 2026)
        self.assertEqual(len(snapshot['subjects']), 60)
        self.assertEqual({item['code']: (item['name'], item['area']) for item in snapshot['subjects']}, SUBJECTS)
        self.assertEqual(len(snapshot['rows']), 21348)
        codes = {row[0] for row in snapshot['rows']}
        self.assertEqual(codes, set(SUBJECTS))
        weights = {item['code']: item['weights'] for item in snapshot['subjects']}
        # The table in subjects.py (what the API uses) is the one in the snapshot.
        self.assertEqual({code: list(values) for code, values in SUBJECT_WEIGHTS.items()}, weights)
        for code, rank, label, name, country, score, *scores in snapshot['rows'][:3000:7]:
            self.assertIsInstance(rank, int)
            self.assertTrue(name and country)
            self.assertTrue(label == '' or str(rank) in label)
            # One score per indicator the subject uses, none for an unused one.
            self.assertEqual(len(scores), sum(1 for weight in weights[code] if weight))


class LoaderTests(TestCase):
    def load(self, *rows, year=2026):
        subjects = [{'code': 'COM02', 'weights': [0.4, 0.3, 0.125, 0.125, 0.05]}, {'code': 'MAT01', 'weights': [0.4, 0.2, 0.15, 0.15, 0.1]}]
        snapshot = {'source': 'QS by Subject 2026', 'year': year, 'subjects': subjects, 'rows': list(rows)}
        output = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'subjects.json'
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            call_command('load_qs_subject_rankings', file=str(path), stdout=output)
        return output.getvalue()

    def setUp(self):
        self.mit = University.objects.create(name='Massachusetts Institute of Technology', country='United States')
        self.michigan = University.objects.create(name='University of Michigan', country='United States')
        self.rows = [
            ['COM02', 1, '', 'Massachusetts Institute of Technology (MIT)', 'United States', 100.0, 94.7, 97.3, 93.6, 94.0, 88.2],
            ['MAT01', 201, '201-250', 'Massachusetts Institute of Technology (MIT)', 'United States', None, 60.0, 50.5, 40.0, 30.0, 20.0],
            ['COM02', 12, '', 'University of Michigan-Ann Arbor', 'United States', 90.5, 80.0, 70.0, 60.0, 50.0, 40.0],
            ['COM02', 5, '', 'Unknown Institute of Nowhere', 'Atlantis', 80.0],
        ]

    def test_snapshot_without_weights_loads_and_reloads_with_empty_indicators(self):
        # An older snapshot has no per-subject weights and no trailing indicator scores.
        snapshot = {'source': 'QS by Subject 2025', 'year': 2025, 'subjects': [{'code': 'COM02'}],
                    'rows': [['COM02', 3, '', 'Massachusetts Institute of Technology (MIT)', 'United States', 90.0]]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.json'
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            call_command('load_qs_subject_rankings', file=str(path), stdout=StringIO())
            snapshot['rows'][0][1] = 4
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            call_command('load_qs_subject_rankings', file=str(path), stdout=StringIO())
        row = UniversitySubjectRank.objects.get(university=self.mit, subject_code='COM02')
        self.assertEqual((row.rank, row.year), (4, 2025))
        for field in ('academic_score', 'employer_score', 'citations_score', 'h_index_score', 'irn_score'):
            self.assertIsNone(getattr(row, field))

    def test_matches_by_key_never_creates_universities_and_reports(self):
        output = self.load(*self.rows)
        self.assertEqual(University.objects.count(), 2)
        self.assertIn('2 of 3 institutions matched', output)
        self.assertIn('1 unmatched', output)
        ranks = {(row.university.name, row.subject_code): (row.rank, row.rank_label, row.score, row.year) for row in UniversitySubjectRank.objects.all()}
        self.assertEqual(ranks, {
            ('Massachusetts Institute of Technology', 'COM02'): (1, '', 100.0, 2026),
            ('Massachusetts Institute of Technology', 'MAT01'): (201, '201-250', None, 2026),
            ('University of Michigan', 'COM02'): (12, '', 90.5, 2026),
        })

    def test_indicator_scores_are_stored_and_an_older_row_without_them_gives_none(self):
        self.load(*self.rows, ['COM02', 30, '', 'University of Michigan-Ann Arbor', 'United States', 70.0])
        row = UniversitySubjectRank.objects.get(subject_code='COM02', university=self.mit)
        self.assertEqual(
            [row.academic_score, row.employer_score, row.citations_score, row.h_index_score, row.irn_score],
            [Decimal('94.7'), Decimal('97.3'), Decimal('93.6'), Decimal('94.0'), Decimal('88.2')],
        )
        # The Michigan COM02 row came twice: the better rank (12) is kept with its scores.
        self.assertEqual(UniversitySubjectRank.objects.get(subject_code='COM02', university=self.michigan).academic_score, Decimal('80.0'))
        self.load(['COM02', 30, '', 'University of Michigan-Ann Arbor', 'United States', 70.0])
        self.assertIsNone(UniversitySubjectRank.objects.get(subject_code='COM02', university=self.michigan).academic_score)

    def test_running_it_again_changes_nothing(self):
        self.load(*self.rows)
        columns = ('pk', 'rank', 'rank_label', 'score', 'academic_score', 'employer_score', 'citations_score', 'h_index_score', 'irn_score')
        before = list(UniversitySubjectRank.objects.order_by('pk').values_list(*columns))
        output = self.load(*self.rows)
        self.assertEqual(list(UniversitySubjectRank.objects.order_by('pk').values_list(*columns)), before)
        self.assertIn('added 0 subject ranks, updated 0, removed 0', output)

    def test_a_changed_indicator_score_is_updated(self):
        self.load(*self.rows)
        self.rows[0][6] = 95.0
        self.assertIn('updated 1', self.load(*self.rows))
        self.assertEqual(UniversitySubjectRank.objects.get(subject_code='COM02', university=self.mit).academic_score, Decimal('95.0'))

    def test_a_changed_rank_is_updated_and_a_dropped_one_removed(self):
        self.load(*self.rows)
        self.rows[0][1] = 2
        del self.rows[1]
        output = self.load(*self.rows)
        self.assertIn('added 0 subject ranks, updated 1, removed 1', output)
        self.assertEqual(UniversitySubjectRank.objects.get(subject_code='COM02', university=self.mit).rank, 2)
        self.assertFalse(UniversitySubjectRank.objects.filter(subject_code='MAT01').exists())

    def test_another_year_is_kept_apart(self):
        self.load(*self.rows)
        self.load(*self.rows[:1], year=2027)
        self.assertEqual(UniversitySubjectRank.objects.filter(year=2026).count(), 3)
        self.assertEqual(UniversitySubjectRank.objects.filter(year=2027).count(), 1)

    def test_the_shipped_snapshot_matches_the_curated_catalogue(self):
        from .catalog_v1 import CATALOG

        for name, country, *_ in CATALOG[:200]:
            University.objects.get_or_create(name=name, country=country)
        output = self.load(*json.loads(DATA_FILE.read_text(encoding='utf-8'))['rows'])
        self.assertIn('matched the catalogue', output)
        self.assertGreater(UniversitySubjectRank.objects.count(), 500)


class MajorMapTests(TestCase):
    def check(self, text, *codes):
        self.assertEqual(subjects_for_major(text), list(codes), text)

    def test_english(self):
        self.check('Computer Science', 'COM02')
        self.check('Business, Economics', 'BUS01', 'ECO01')
        self.check('Mechanical Engineering', 'ENG05')
        self.check('Data Science and AI', 'DAT01')
        self.check('Veterinary Medicine', 'VET01')
        self.check('Physics; Mathematics', 'PHY01', 'MAT01')
        self.check('Law / International Relations', 'LAW01', 'POL01')

    def test_russian(self):
        self.check('информатика', 'COM02')
        self.check('Экономика и финансы', 'ECO01', 'ACC01')
        self.check('Юриспруденция', 'LAW01')
        self.check('Психология', 'PSY01')

    def test_uzbek_latin_with_both_apostrophes(self):
        self.check('kompyuter injiniringi', 'COM02')
        self.check('Iqtisodiyot va menejment', 'ECO01', 'BUS01')
        self.check('tibbiyot', 'MED01')
        self.check('Huquqshunoslik', 'LAW01')
        self.check('o‘qituvchi', 'EDU01')
        self.check("o'qituvchi", 'EDU01')
        self.check('sun’iy intellekt', 'DAT01')

    def test_a_broad_area_only_when_no_subject_matches_else_nothing(self):
        self.check('Engineering', 'AREA_ENG')
        self.check('Humanities', 'AREA_ART')
        self.check('Underwater basket weaving')
        self.check('')
        self.check(None)

    def test_a_subject_beats_an_area_and_the_longest_keyword_wins(self):
        self.check('Electrical engineering', 'ENG03')
        self.check('Chemical engineering', 'ENG01')
        self.check('Chemistry', 'CHE01')
        self.check('Art history', 'HIS02')

    def test_splitting_and_repeats(self):
        self.assertEqual(split_majors('Business and Economics, Law'), ['business', 'economics', 'law'])
        self.check('Economics, economics / Экономика', 'ECO01')

    def test_compound_subject_names_match_whole_before_splitting(self):
        self.check('Oil and Gas', 'PET01')
        self.check('Oil & Gas Engineering', 'PET01')
        self.check('Hospitality & Leisure Management', 'HOS01')
        self.check('Computer Science & Information Systems', 'COM02')

    def test_two_real_majors_still_give_both(self):
        self.check('Economics and Computer Science', 'ECO01', 'COM02')
        self.check('Oil and Gas and Law', 'PET01', 'LAW01')

    def test_every_keyword_code_is_a_subject(self):
        from .subjects import KEYWORDS

        self.assertEqual(set(KEYWORDS) - set(SUBJECTS), set())
        self.assertEqual(sorted(set(SUBJECTS) - set(KEYWORDS)), [])
