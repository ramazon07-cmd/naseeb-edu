"""Rebuild the QS World University Rankings snapshot from QS's spreadsheet.

    backend/.venv/bin/python scripts/build_qs_catalog.py "2027 QS World University Rankings 1.3 (For qs.com).xlsx"

It rewrites backend/apps/admissions/catalog_data/qs_world_university_rankings_2027.json,
which `python manage.py load_qs_rankings` loads. Preserve classifications,
published ranks and every indicator score without inventing admission data.
"""
import json
import re
import sys
from pathlib import Path

import openpyxl

SOURCE = 'QS World University Rankings 2027'
SOURCE_URL = 'https://www.topuniversities.com/world-university-rankings'
TARGET = Path(__file__).resolve().parents[1] / 'backend/apps/admissions/catalog_data/qs_world_university_rankings_2027.json'

# QS's official names -> the names students know (and pick in onboarding: 'Turkey', 'Vietnam').
COUNTRY_NAMES = {
    'United States of America': 'United States',
    'China (Mainland)': 'China',
    'Hong Kong SAR, China': 'Hong Kong',
    'Macao SAR, China': 'Macao',
    'Republic of Korea': 'South Korea',
    'Russian Federation': 'Russia',
    'Türkiye': 'Turkey',
    'Viet Nam': 'Vietnam',
    'Iran (Islamic Republic of)': 'Iran',
    'Venezuela (Bolivarian Republic of)': 'Venezuela',
    'Syrian Arab Republic': 'Syria',
    'Brunei Darussalam': 'Brunei',
}
TYPES = {'Public': 'public', 'Private not for Profit': 'private', 'Private for Profit': 'private'}
INDICATORS = ('AR', 'ER', 'FSR', 'CPF', 'IFR', 'ISR', 'IRN', 'EO', 'SUS')


def score_of(value):
    """Missing published scores stay null; a numeric zero is a real score."""
    if value is None or str(value).strip() in ('', '-', '—'):
        return None
    score = float(value)
    if not 0 <= score <= 100:
        raise ValueError(f'Invalid QS score: {value}')
    return score


def qs_details(row, column):
    return {
        'year': 2027,
        'source_url': SOURCE_URL,
        'previous_rank': clean(row[column['Previous Rank']]),
        **{key.lower(): clean(row[column[key]]) for key in ('Region', 'Size', 'Focus', 'Research', 'Status')},
        'overall_score': score_of(row[column['Overall SCORE']]),
        'indicators': {
            code: {'score': score_of(row[column[f'{code} SCORE']]), 'rank': clean(row[column[f'{code} RANK']])}
            for code in INDICATORS
        },
    }


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def rank_of(value):
    """12 -> (12, ''); '701-710' -> (701, '701-710'); '1401+' -> (1401, '1401+')."""
    if isinstance(value, int):
        return value, ''
    label = clean(value)
    return int(re.match(r'\d+', label).group()), label


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    rows = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True).active.iter_rows(values_only=True)
    header = next(row for row in rows if 'Name' in row and 'Country/Territory' in row)
    column = {title: index for index, title in enumerate(header) if title}
    universities = []
    for row in rows:
        name = clean(row[column['Name']])
        if not name:
            continue
        country = clean(row[column['Country/Territory']])
        rank, rank_label = rank_of(row[column['Rank']])
        universities.append({
            'name': name,
            'country': COUNTRY_NAMES.get(country, country),
            'rank': rank,
            'rank_label': rank_label,
            'type': TYPES.get(clean(row[column['Status']]), ''),
            'qs_data': qs_details(row, column),
        })
    pairs = [(item['name'], item['country']) for item in universities]
    if len(set(pairs)) != len(pairs):
        sys.exit('The spreadsheet lists a university twice.')
    lines = ',\n'.join(f'  {json.dumps(item, ensure_ascii=False)}' for item in universities)
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(
        f'{{\n "source": {json.dumps(SOURCE)},\n "source_url": {json.dumps(SOURCE_URL)},\n "universities": [\n{lines}\n ]\n}}\n',
        encoding='utf-8',
    )
    print(f'Wrote {len(universities)} universities to {TARGET}')


if __name__ == '__main__':
    main()
