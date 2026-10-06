"""Rebuild the College Scorecard snapshot for the catalogue's US universities.

    curl -sSLO https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_06102026.zip
    unzip Most-Recent-Cohorts-Institution_06102026.zip
    python3 scripts/build_scorecard_catalog.py Most-Recent-Cohorts-Institution.csv

It reads the US universities of the QS snapshot, finds each one in the U.S.
Department of Education's College Scorecard (public domain) and rewrites
backend/apps/admissions/catalog_data/college_scorecard_2026.json, which
`python manage.py load_college_scorecard` loads. The net price is Scorecard's
average net price (NPT4_PUB for public universities, NPT4_PRIV otherwise);
the full yearly cost of attendance (COSTT4_A) is kept separately as cost_usd.
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'backend/apps/admissions/catalog_data'
QS_SNAPSHOT = DATA / 'qs_world_university_rankings_2027.json'
TARGET = DATA / 'college_scorecard_2026.json'
SOURCE = 'U.S. Department of Education College Scorecard, Most Recent Institution-Level Data (10 June 2026)'
SOURCE_URL = 'https://collegescorecard.ed.gov/data/'

# QS names whose Scorecard entry is a named campus (or spelled differently).
# City University of New York is a system of colleges with no single entry, so it stays unmatched.
SCORECARD_NAMES = {
    'Columbia University': 'Columbia University in the City of New York',
    'University of Washington': 'University of Washington-Seattle Campus',
    'Texas A&M University': 'Texas A&M University-College Station',
    'University of Minnesota (System)': 'University of Minnesota-Twin Cities',
    'University of Pittsburgh': 'University of Pittsburgh-Pittsburgh Campus',
    'North Carolina State University': 'North Carolina State University at Raleigh',
    'University at Buffalo SUNY': 'University at Buffalo',
    'Stony Brook University, State University of New York': 'Stony Brook University',
    'Colorado State University': 'Colorado State University-Fort Collins',
    'Tulane University': 'Tulane University of Louisiana',
    'University of Hawaiʻi at Mānoa': 'University of Hawaii at Manoa',
    'University of South Carolina': 'University of South Carolina-Columbia',
    'University of Oklahoma': 'University of Oklahoma-Norman Campus',
    'The New School, New York City and Paris': 'The New School',
    'University of Colorado Denver | Anschutz Medical Campus': 'University of Colorado Denver/Anschutz Medical Campus',
    'Louisiana State University': 'Louisiana State University and Agricultural & Mechanical College',
    'University at Albany SUNY': 'University at Albany',
    'Binghamton University SUNY': 'Binghamton University',
    'Florida Atlantic University - Boca Raton': 'Florida Atlantic University',
    'Kent State University': 'Kent State University at Kent',
    'Miami University': 'Miami University-Oxford',
    'University of Arkansas Fayetteville': 'University of Arkansas',
    'University of Texas El Paso': 'The University of Texas at El Paso',
    'California Polytechnic State University': 'California Polytechnic State University-San Luis Obispo',
}
# Scorecard LOCALE: 1x city, 2x suburb, 3x town (no matching choice), 4x rural.
SETTINGS = {'1': 'urban', '2': 'suburban', '4': 'rural'}


def key(name):
    """'University of California, Berkeley (UCB)' and 'University of California-Berkeley' meet."""
    value = re.sub(r'[–—]', ' ', name)  # dashes would vanish with the accents below
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    value = re.sub(r'\([^)]*\)', ' ', value).replace('&', ' and ')
    value = re.sub(r'[-/,.\'|]', ' ', value)
    value = re.sub(r'^the ', '', re.sub(r'\s+', ' ', value).strip())
    return re.sub(r' (main campus|campus immersion)$', '', value)


def number(value, cast=int):
    try:
        return cast(value)
    except (TypeError, ValueError):  # 'NA', 'PrivacySuppressed', ''
        return None


def details(row):
    scores = [number(row[column]) for column in ('SATVR25', 'SATMT25', 'SATVR75', 'SATMT75')]
    acceptance = number(row['ADM_RATE'], float)
    website = re.sub(r'^https?://', '', row['INSTURL'].strip())
    return {
        'acceptance_rate': round(acceptance * 100, 2) if acceptance is not None else None,
        'sat_min': scores[0] + scores[1] if None not in scores else None,
        'sat_max': scores[2] + scores[3] if None not in scores else None,
        'act_min': number(row['ACTCM25']),
        'act_max': number(row['ACTCM75']),
        # ADMCON7: 1 required, 2 recommended, 3 neither, 5 considered but not required.
        'test_optional': {'1': False, '2': True, '3': True, '5': True}.get(row['ADMCON7']),
        'cost_usd': number(row['COSTT4_A']),
        # CONTROL: 1 public, 2 private nonprofit, 3 private for-profit.
        'net_price_usd': number(row['NPT4_PUB'] if row['CONTROL'] == '1' else row['NPT4_PRIV']),
        'tuition_usd': number(row['TUITIONFEE_OUT']),
        'undergrad_enrollment': number(row['UGDS']),
        'city': f"{row['CITY']}, {row['STABBR']}" if row['CITY'] else None,
        'website': f'https://{website}' if '.' in website else None,
        'campus_setting': SETTINGS.get(row['LOCALE'][:1]),
    }


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    csv.field_size_limit(sys.maxsize)
    with open(sys.argv[1], newline='', encoding='utf-8-sig') as source:
        rows = [row for row in csv.DictReader(source) if row['ICLEVEL'] == '1' and row['CURROPER'] == '1']
    by_name = {row['INSTNM']: row for row in rows}
    by_key = {}
    for row in rows:
        by_key.setdefault(key(row['INSTNM']), []).append(row)
    universities, missing = [], []
    for university in json.loads(QS_SNAPSHOT.read_text(encoding='utf-8'))['universities']:
        if university['country'] != 'United States':
            continue
        name = university['name']
        candidates = [by_name[SCORECARD_NAMES[name]]] if name in SCORECARD_NAMES else by_key.get(key(name), [])
        if not candidates:
            missing.append(name)
            continue
        # Same name in several places: the main campus, then the largest.
        row = max(candidates, key=lambda item: (item['MAIN'] == '1', number(item['UGDS']) or 0))
        universities.append({'name': name, 'unitid': int(row['UNITID']), **{field: value for field, value in details(row).items() if value is not None}})
    lines = ',\n'.join(f'  {json.dumps(item, ensure_ascii=False)}' for item in universities)
    TARGET.write_text(
        f'{{\n "source": {json.dumps(SOURCE)},\n "source_url": {json.dumps(SOURCE_URL)},\n "universities": [\n{lines}\n ]\n}}\n',
        encoding='utf-8',
    )
    print(f'Wrote {len(universities)} universities to {TARGET}; not in College Scorecard: {missing or "none"}')


if __name__ == '__main__':
    main()
