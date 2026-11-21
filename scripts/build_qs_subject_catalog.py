"""Rebuild the QS World University Rankings by Subject snapshot from QS's spreadsheet.

    backend/.venv/bin/python scripts/build_qs_subject_catalog.py "qs_world_university_rankings_by_subject_2026_-_public_results.xlsx"

It rewrites backend/apps/admissions/catalog_data/qs_subject_rankings_2026.json, which
`python manage.py load_qs_subject_rankings` loads. The 55 subjects and the 5 broad areas
(codes AREA_*) are kept with every published rank and indicator score; nothing is invented.
Each row ends with the scores of the indicators the subject uses, in the order of the
subject's "weights" (Academic, Employer, Citations per paper, H index, International
research network); an indicator with weight 0 is not published and not stored. openpyxl is needed
by this script only, not by the app.
"""
import json
import re
import sys
from itertools import islice
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_qs_catalog import COUNTRY_NAMES, clean  # noqa: E402

SOURCE = 'QS World University Rankings by Subject 2026'
SOURCE_URL = 'https://www.topuniversities.com/subject-rankings'
YEAR = 2026
TARGET = Path(__file__).resolve().parents[1] / 'backend/apps/admissions/catalog_data/qs_subject_rankings_2026.json'

# Methodology SUBJECT_CODE of a broad area -> our code, in workbook order.
AREAS = {
    'F-ART': 'AREA_ART', 'F-ENG': 'AREA_ENG', 'F-LIF': 'AREA_LIF', 'F-NAT': 'AREA_NAT', 'F-SOC': 'AREA_SOC',
}
# Sheet names are cut to 31 characters and cannot hold '/'; two are renamed outright.
SHEET_OVERRIDES = {'History': 'History_Subject'}


def sheet_name(subject_name):
    return SHEET_OVERRIDES.get(subject_name) or subject_name.replace('/', '_')[:31]


def subjects_of(workbook):
    """``[(code, name, area_code, sheet)]``: subjects after their broad area, then the areas themselves."""
    methodology = list(workbook['methodology'].iter_rows(min_row=2, values_only=True))
    by_sheet = {}
    for _, code, name, *_ in methodology:
        if code:
            by_sheet[sheet_name(clean(name))] = (clean(code), clean(name))
    missing = [sheet for sheet in workbook.sheetnames[2:] if sheet not in by_sheet]
    if missing:
        sys.exit(f'Sheets without a methodology row: {missing}')
    subjects, area = [], None
    for sheet in workbook.sheetnames[2:]:
        code, name = by_sheet[sheet]
        if code in AREAS:
            area = AREAS[code]
            subjects.append((area, name, area, sheet))
        else:
            subjects.append((code, name, area, sheet))
    return subjects


def rank_of(value):
    """12 -> (12, ''); '201-250' -> (201, '201-250'); '=51' -> (51, '=51'): the lower bound and the label as published."""
    if isinstance(value, (int, float)):
        return int(value), ''
    label = clean(value)
    return int(re.search(r'\d+', label).group()), label


def score_of(value):
    if value is None or str(value).strip() in ('', '-', '—'):
        return None
    return float(value)


# Workbook columns of the five indicator scores, in the order of the sheet's weight row (F..J).
INDICATOR_COLUMNS = ('ACADEMIC', 'EMPLOYER', 'CITATIONS', 'H', 'IRN')


def weights_of(sheet):
    """The five indicator weights QS prints above the table (0 when a subject does not use one)."""
    row = next(islice(sheet.iter_rows(values_only=True), 1, 2))
    return [round(float(value or 0), 4) for value in row[5:10]]


def sheet_rows(sheet, code, weights):
    rows = sheet.iter_rows(values_only=True)
    header = next(row for row in rows if row and row[2] == 'INSTITUTION')
    column = {title: index for index, title in enumerate(header) if title}
    for row in rows:
        name = clean(row[column['INSTITUTION']])
        if not name or row[column['2026']] is None:
            continue
        country = clean(row[column['COUNTRY/TERRITORY']])
        rank, label = rank_of(row[column['2026']])
        scores = [score_of(row[column[title]]) for title, weight in zip(INDICATOR_COLUMNS, weights) if weight]
        yield [code, rank, label, name, COUNTRY_NAMES.get(country, country), score_of(row[column['SCORE']]), *scores]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    workbook = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
    subjects = subjects_of(workbook)
    rows, weights = [], {}
    for code, _, _, sheet in subjects:
        weights[code] = weights_of(workbook[sheet])
        rows.extend(sheet_rows(workbook[sheet], code, weights[code]))
    seen = set()
    for row in rows:
        key = (row[0], row[3], row[4])
        if key in seen:
            sys.exit(f'The spreadsheet lists {row[3]} twice in {row[0]}.')
        seen.add(key)
    head = {'source': SOURCE, 'source_url': SOURCE_URL, 'year': YEAR,
            'subjects': [{'code': code, 'name': name, 'area': area, 'weights': weights[code]} for code, name, area, _ in subjects]}
    lines = ',\n'.join(f'  {json.dumps(row, ensure_ascii=False)}' for row in rows)
    TARGET.parent.mkdir(exist_ok=True)
    body = json.dumps(head, ensure_ascii=False)[:-1]
    TARGET.write_text(f'{body}, "rows": [\n{lines}\n ]}}\n', encoding='utf-8')
    print(f'Wrote {len(rows)} rows for {len(subjects)} subjects to {TARGET}')


if __name__ == '__main__':
    main()
