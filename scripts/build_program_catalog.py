"""Rebuild the program catalog snapshot from the counselor spreadsheet.

    curl -sL -o /tmp/programs.xlsx \
      "https://docs.google.com/spreadsheets/d/<sheet id>/export?format=xlsx"
    backend/.venv/bin/python scripts/build_program_catalog.py /tmp/programs.xlsx

It rewrites the `programs` list inside the newest
backend/apps/admissions/migrations/catalog_data/portal_catalog_*.json. Editing the
snapshot of a migration that already shipped changes nothing in a database that ran
it; add a new migration with the new snapshot for that.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import openpyxl

SOURCE = 'https://docs.google.com/spreadsheets/d/1GkmkRPHMiX_CYtnrrsKbk7WrV_J3fNuOEKOk0GPi3NE/edit'
REVIEWED = '2026-09-20'
GENERIC_HOSTS = {'forms.gle', 'docs.google.com', 'airtable.com', 'sites.google.com', 'rsip.carrd.co'}
UZBEK_MARKERS = ('olimpiyada', 'xalqaro', 'iqtisodiyot')

CATEGORY_RULES = [
    ('Competition', ('competition', 'challenge', 'prize', 'award', 'cup', 'contest',
                     'olympiad', 'olimpiyada', 'brawl', 'tournament', 'hackathon', 'championship')),
    ('Conference', ('forum', 'summit', 'conference', 'congress', 'exchange')),
    ('Fellowship', ('fellowship', 'fellow', 'internship')),
    ('Summer program', ('summer', 'camp', 'immersion', 'precollege', 'pre-collegiate', 'seminar')),
    ('Leadership', ('leader', 'ambassador', 'diplomacy')),
    ('Scholarship', ('scholarship',)),
    ('Research', ('research', 'scholars', 'science', 'academics', 'institute', 'academy')),
]


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('|', ' — ')).strip()


def grade_numbers(text):
    """'8-10' -> [8, 9, 10]; '5-11' -> [5..11]."""
    match = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        return list(range(low, high + 1))
    return [int(part) for part in re.findall(r'\d+', text)]


def category_for(title):
    lowered = title.lower()
    for name, keywords in CATEGORY_RULES:
        if any(word in lowered for word in keywords):
            return name
    return 'Program'


def provider_for(url):
    host = urlparse(url).netloc.lower().removeprefix('www.')
    return '' if not host or host in GENERIC_HOSTS else host


def key_for(title):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:88]
    return f'sheet-{slug}'


def iso_deadline(text):
    match = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})$', text)
    return date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat() if match else None


def main():
    source = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/programs.xlsx')
    workbook = openpyxl.load_workbook(source, data_only=True)
    programs = {}

    def merge(title, *, ages, grades, opens, closes, url, sheet, row, refreshed=False):
        title = clean(title)
        if not title or title.lower() == 'program name':
            return
        key = key_for(title)
        entry = programs.setdefault(key, {
            'source_key': key, 'title': title, 'grades': set(), 'eligible_ages': '',
            'application_open_text': '', 'deadline_text': '', 'deadline': None,
            'application_url': '', 'sheets': [], 'refreshed': False,
        })
        entry['grades'].update(grades)
        entry['sheets'].append(f'{sheet}!{row}')
        fresher = refreshed or not entry['refreshed']
        if fresher:
            entry['refreshed'] = entry['refreshed'] or refreshed
            for field, value in (('eligible_ages', clean(ages)),
                                 ('application_open_text', clean(opens)),
                                 ('deadline_text', clean(closes)),
                                 ('application_url', clean(url))):
                if value and (refreshed or not entry[field]):
                    entry[field] = value
            parsed = iso_deadline(clean(closes))
            if parsed and (refreshed or not entry['deadline']):
                entry['deadline'] = parsed

    for sheet in workbook.worksheets:
        name = sheet.title.strip()
        sheet_grades = grade_numbers(name) if name.lower().startswith(('grade', 'gerade')) else []
        for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            cells = [clean(cell) for cell in row] + [''] * 6
            if index == 1 or not cells[0]:
                continue
            if name == 'Sheet10':
                merge(cells[0], ages=cells[1], grades=grade_numbers(cells[2]), opens=cells[3],
                      closes=cells[4], url=cells[5], sheet=name, row=index, refreshed=True)
            elif name == 'Summer programs':
                merge(cells[0], ages=cells[1] if not cells[1][:4].isdigit() else '', grades=[],
                      opens='', closes=cells[2], url='', sheet=name, row=index)
            elif name == 'deadline':
                merge(cells[0], ages='', grades=[], opens='', closes=cells[1], url=cells[2],
                      sheet=name, row=index)
            else:
                merge(cells[0], ages=cells[1], grades=sheet_grades, opens=cells[2],
                      closes=cells[3], url=cells[4], sheet=name, row=index)

    catalog = []
    for entry in programs.values():
        title = entry['title']
        national = any(marker in title.lower() for marker in UZBEK_MARKERS)
        catalog.append({
            'source_key': entry['source_key'],
            'title': title,
            'provider': provider_for(entry['application_url']),
            'program_type': 'national' if national else 'international',
            'category': category_for(title),
            'delivery_mode': 'unspecified',
            'eligible_ages': entry['eligible_ages'][:160],
            'eligible_grades': ','.join(str(grade) for grade in sorted(entry['grades'])),
            'deadline': entry['deadline'],
            'deadline_text': entry['deadline_text'],
            'application_open_text': entry['application_open_text'],
            'application_url': entry['application_url'],
            'source_url': SOURCE,
            'source_metadata': {'sheets': entry['sheets'], 'reviewed_on': REVIEWED},
            'needs_verification': entry['deadline'] is None,
        })

    catalog.sort(key=lambda item: item['title'].lower())
    print(f'{len(catalog)} programs, {sum(1 for item in catalog if item["deadline"])} with a dated deadline')
    for item in catalog:
        if not item['application_url']:
            print('  no link:', item['title'])
    target = sorted((Path(__file__).parent.parent / 'backend/apps/admissions/migrations/catalog_data').glob('portal_catalog_*.json'))[-1]
    snapshot = json.loads(target.read_text(encoding='utf-8'))
    # rows imported from the PDF compilations carry their own keys and are kept
    others = [row for row in snapshot['programs'] if not row['source_key'].startswith('sheet-')]
    snapshot['programs'] = catalog + others
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('wrote', target)


if __name__ == '__main__':
    main()
