"""Run with the Python runtime containing openpyxl."""
import unittest

from build_qs_catalog import INDICATORS, qs_details, score_of


class QsSpreadsheetParsingTests(unittest.TestCase):
    def test_missing_scores_are_not_zero_and_scores_stay_in_range(self):
        for value in (None, '', '-', '—'):
            self.assertIsNone(score_of(value))
        self.assertEqual(score_of(0), 0)
        self.assertEqual(score_of('99.2'), 99.2)
        for value in (-1, 101, 'NaN'):
            with self.assertRaises(ValueError):
                score_of(value)

    def test_all_classifications_and_published_rank_labels_survive(self):
        values = {'Previous Rank': '1201-1400', 'Region': 'Asia', 'Size': 'M', 'Focus': 'FC', 'Research': 'HI', 'Status': 'Public', 'Overall SCORE': '-'}
        for code in INDICATORS:
            values[f'{code} SCORE'] = 0 if code == 'AR' else 85.4
            values[f'{code} RANK'] = '7=' if code == 'SUS' else '701+'
        data = qs_details(list(values.values()), {key: i for i, key in enumerate(values)})
        self.assertEqual(len(data['indicators']), 9)
        self.assertEqual(data['previous_rank'], '1201-1400')
        self.assertEqual(data['indicators']['AR'], {'score': 0, 'rank': '701+'})
        self.assertEqual(data['indicators']['SUS']['rank'], '7=')
        self.assertEqual((data['region'], data['size'], data['focus'], data['research']), ('Asia', 'M', 'FC', 'HI'))
        self.assertIsNone(data['overall_score'])


if __name__ == '__main__':
    unittest.main()
