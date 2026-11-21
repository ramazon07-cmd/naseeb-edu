"""The college match: ten universities for the student's major, chosen by fixed rules (no AI).

The same profile always gives the same list. Every step is a rule over catalogue data:

1. The student's target major (free text) maps to QS subjects (subjects.py). With none mapped the
   overall QS rank is used and the student is told to pick a major.
2. Candidates are the universities with a QS 2026 subject rank in any of those subjects, in the
   student's target countries. Universities without a subject rank whose popular majors name the
   major may follow the ranked ones.
3. Aid and cost gates (``passes_gate``) drop universities a student who needs money cannot afford.
4. The chance band comes from admission_chance.chance with the academics score only: activities and
   essays are neutral there, so they never change who is listed or the band.
5. Within a band: subject rank, then aid for international students, then international admit rate,
   then overall QS rank, then name.
6. Three reach (reach, then far reach), four target and three safety universities. A short band is
   filled from the nearest band and the response says so.
"""
from django.db.models import Max

from . import admission_chance
from .college_search import SCORING_FIELDS, country_match, eligible_programs, fit_context, has_aid_data, serialize_rows
from .models import University, UniversitySubjectRank
from .pricing import with_cost
from .subjects import SUBJECTS, split_majors, subject_name, subjects_for_major

# (group, how many, the bands it takes first-to-last).
MATCH_GROUPS = (
    ('reach', 3, (admission_chance.REACH, admission_chance.FAR_REACH)),
    ('target', 4, (admission_chance.TARGET,)),
    ('safety', 3, (admission_chance.SAFETY,)),
)
# Where a short group takes its missing universities from, nearest first.
FILL_ORDER = {'reach': ('target', 'safety'), 'target': ('reach', 'safety'), 'safety': ('target', 'reach')}
MATCH_PROGRAMS = 2
COST_CAP_FACTOR = 2
AID_ORDER = {'yes': 0, 'need_aware': 1, 'merit': 2, 'none': 3, 'unknown': 4}
NO_RANK = 10 ** 9
MATCH_FIELDS = (*SCORING_FIELDS, 'name', 'ranking_label', 'tuition_usd')


def aid_status(university):
    """What the catalogue says about aid for a student from abroad: yes, need_aware, merit, none or unknown."""
    policy = university.intl_need_policy
    if policy == University.IntlNeedPolicy.NEED_BLIND or (
        university.offers_international_aid and (university.meets_full_need or university.need_blind)
    ):
        return 'yes'
    if policy == University.IntlNeedPolicy.NEED_AWARE:
        return 'need_aware'
    if university.offers_international_aid:
        return 'yes'
    if university.offers_merit_aid:
        return 'merit'
    return 'none' if has_aid_data(university) else 'unknown'


def gives_international_aid(university):
    return bool(university.offers_international_aid or university.intl_need_policy)


def international_cost(university):
    """What a student from abroad pays per year: the one cost rule (pricing.py), else the tuition outside the US.

    A US row without an international cost stays unpriced: its net price is what US students pay after aid.
    """
    if university.cost is not None:
        return university.cost
    if university.market == University.Market.US:
        return None
    return university.tuition_usd


def passes_gate(university, cost, ctx):
    """The aid and cost gate for a student's budget.

    * Needs a scholarship and the university gives none to students from abroad: kept only when it
      is known to cost no more than the budget (an unknown cost or budget drops it).
    * Costs more than twice the budget and gives no aid to students from abroad: dropped.
    """
    if gives_international_aid(university):
        return True
    budget = ctx['budget']
    if ctx['scholarship_needed'] and (cost is None or budget is None or cost > budget):
        return False
    return not (cost is not None and budget is not None and cost > COST_CAP_FACTOR * budget)


def sat_position(university, sat):
    """The student's SAT against the university's published range: below, inside or above, with the numbers."""
    low, high = university.sat_min, university.sat_max
    if not low:
        return {'position': 'no_range', 'score': sat, 'min': None, 'max': None}
    if sat is None:
        return {'position': 'no_score', 'score': None, 'min': low, 'max': high}
    position = 'below' if sat < low else 'above' if high and sat > high else 'inside'
    return {'position': position, 'score': sat, 'min': low, 'max': high}


def budget_position(cost, budget):
    if cost is None:
        return 'unknown'
    if budget is None:
        return 'no_budget'
    return 'within' if cost <= budget else 'over'


def rank_label(rank, label):
    return label.lstrip('=') if label else str(rank)


def covers(student_code, program_code):
    """A program subject answers a student's subject when equal, or when the student named a broad area."""
    return student_code == program_code or (student_code.startswith('AREA_') and SUBJECTS[program_code][1] == student_code)


def suggested_programs(university, majors):
    """Up to two of the university's eligible programs for the stated majors, by rule: a program matches a major
    when the two texts contain one another or when both map to the same QS subject. Majors keep the student's order."""
    found = []
    for major in majors:
        wanted = subjects_for_major(major)
        for program in university.programs.all():
            name = program.canonical_major.strip().lower()
            if not name or any(program.name == item['name'] for item in found):
                continue
            theirs = subjects_for_major(name)
            if major in name or name in major or any(covers(mine, other) for mine in wanted for other in theirs):
                found.append({'name': program.name, 'canonical_major': program.canonical_major})
    return found[:MATCH_PROGRAMS]


def intended_majors(profile):
    return split_majors(profile.target_major)


def latest_year():
    return UniversitySubjectRank.objects.aggregate(year=Max('year'))['year']


def candidates(subject_codes, majors, ctx):
    """``{university id: pick}`` for the subjects: the best subject rank of each ranked university, then
    unranked universities whose popular majors name one of the student's subjects (rank None)."""
    countries = ctx['countries']
    picks = {}
    year = latest_year()
    if subject_codes and year:
        order = {code: index for index, code in enumerate(subject_codes)}
        for pk, code, rank, label, score in UniversitySubjectRank.objects.filter(
            year=year, subject_code__in=subject_codes,
        ).values_list('university_id', 'subject_code', 'rank', 'rank_label', 'score'):
            pick = {'code': code, 'rank': rank, 'label': label, 'score': score, 'year': year}
            current = picks.get(pk)
            if current is None or (rank, order[code]) < (current['rank'], order[current['code']]):
                picks[pk] = pick
    elif not subject_codes:
        for pk, rank, label in University.objects.filter(ranking__isnull=False).values_list('pk', 'ranking', 'ranking_label'):
            picks[pk] = {'code': None, 'rank': rank, 'label': label, 'score': None, 'year': None}
    if subject_codes:
        for pk, popular in University.objects.exclude(popular_majors='').exclude(pk__in=picks).values_list('pk', 'popular_majors'):
            hits = [code for code in subject_codes if any(covers(code, other) for other in subjects_for_major(popular))]
            if hits or any(major in popular.lower() for major in majors):
                picks[pk] = {'code': (hits or subject_codes)[0], 'rank': None, 'label': '', 'score': None, 'year': None}
    # Target countries, as College Search reads them ('Europe' also matches the QS region).
    meta = University.objects.filter(pk__in=list(picks)).values_list('pk', 'country', 'qs_data__region')
    allowed = {pk for pk, country, region in meta if country_match(_Place(country, region), countries)}
    return {pk: pick for pk, pick in picks.items() if pk in allowed}


class _Place:
    """The two facts ``country_match`` reads, without loading the whole university row."""

    def __init__(self, country, region):
        self.country, self.qs_data = country, {'region': region}


def sort_key(university, pick, status):
    rate = university.intl_acceptance_rate
    return (
        pick['rank'] if pick['rank'] is not None else NO_RANK,
        AID_ORDER[status],
        0 if rate is not None else 1, -float(rate or 0),
        university.ranking or NO_RANK,
        university.name.lower(), university.pk,
    )


def pick_list(entries):
    """``(groups, notes)``: 3 reach, 4 target, 3 safety; a short group is filled from the nearest group."""
    pools = {}
    for group, _, bands in MATCH_GROUPS:
        pool = [entry for band in bands for entry in sorted(
            (entry for entry in entries if entry['band'] == band), key=lambda entry: entry['key'])]
        pools[group] = pool
    chosen = {group: pools[group][:quota] for group, quota, _ in MATCH_GROUPS}
    spare = {group: pools[group][quota:] for group, quota, _ in MATCH_GROUPS}
    notes = []
    for group, quota, _ in MATCH_GROUPS:
        for donor in FILL_ORDER[group]:
            missing = quota - len(chosen[group])
            if missing <= 0 or not spare[donor]:
                continue
            taken, spare[donor] = spare[donor][:missing], spare[donor][missing:]
            chosen[group] += taken
            notes.append({
                'code': 'filled_from', 'params': {'group': group, 'from': donor, 'count': len(taken)},
                'text': f'Only {len(chosen[group]) - len(taken)} {group} universities fit your profile, so {len(taken)} from the {donor} group were added',
            })
    total = sum(len(rows) for rows in chosen.values())
    if total < sum(quota for _, quota, _ in MATCH_GROUPS):
        notes.append({'code': 'short_list', 'params': {'count': total}, 'text': f'Only {total} universities fit your profile and budget'})
    return chosen, notes


def match_with_context(profile):
    """``(match, ctx)``: the list of ten and the fit context it was built from."""
    ctx = fit_context(profile)
    subject_codes = subjects_for_major(profile.target_major)
    ctx['budget'] = profile.budget_usd
    # Academics only: activities and essays stay neutral (None) in the chance engine.
    chance_ctx = {**ctx, 'rubric': {'academics': ctx['rubric']['academics']}}
    majors = intended_majors(profile)
    picks = candidates(subject_codes, majors, ctx)
    universities = with_cost(University.objects.only(*MATCH_FIELDS)).filter(pk__in=list(picks))
    entries, no_aid_listed, no_band = [], 0, 0
    for university in universities:
        cost = international_cost(university)
        if not passes_gate(university, cost, ctx):
            no_aid_listed += aid_status(university) == 'unknown'
            continue
        band = admission_chance.chance(university, chance_ctx)['band']
        if band not in admission_chance.STEPS:
            no_band += band is None
            continue
        status = aid_status(university)
        pick = picks[university.pk]
        entries.append({
            'id': university.pk, 'band': band, 'pick': pick, 'status': status, 'cost': cost,
            'key': sort_key(university, pick, status),
        })
    chosen, notes = pick_list(entries)
    if no_aid_listed and ctx['scholarship_needed']:
        notes.append({
            'code': 'aid_unlisted', 'params': {'count': no_aid_listed},
            'text': f'{no_aid_listed} universities were left out because the catalogue lists no aid for students from abroad',
        })
    if no_band:
        notes.append({
            'code': 'no_admission_data', 'params': {'count': no_band},
            'text': f'{no_band} universities were left out because the catalogue has no admission data to place them',
        })
    ids = [entry['id'] for rows in chosen.values() for entry in rows]
    full = list(with_cost(University.objects.prefetch_related(eligible_programs())).filter(pk__in=ids))
    serialized = {row['id']: row for row in serialize_rows(full, chance_ctx)}
    programs = {university.pk: suggested_programs(university, majors) for university in full}
    by_pk = {university.pk: university for university in full}
    for rows in chosen.values():
        for entry in rows:
            row = serialized[entry['id']]
            row['suggested_programs'] = programs[entry['id']]
            row['factors'] = [{'key': 'academics', 'score': ctx['rubric']['academics'], 'share': 100}]
            row.update(card_facts(by_pk[entry['id']], entry, ctx))
    hints = []
    if not subject_codes:
        hints.append({'code': 'pick_major', 'params': {}, 'text': 'Pick your major for a better list'})
    elif all(code.startswith('AREA_') for code in subject_codes):
        hints.append({'code': 'broad_area', 'params': {}, 'text': 'Name a specific major for a sharper list'})
    return {
        'rubric': ctx['rubric'],
        'subjects': [{'code': code, 'name': subject_name(code)} for code in subject_codes],
        'hints': hints,
        'notes': notes,
        'groups': [
            {'band': group, 'quota': quota, 'results': [serialized[entry['id']] for entry in chosen[group]]}
            for group, quota, _ in MATCH_GROUPS
        ],
    }, ctx


def card_facts(university, entry, ctx):
    pick, cost = entry['pick'], entry['cost']
    if pick['code'] is None:
        subject = {'code': None, 'name': None, 'rank': university.ranking, 'rank_label': rank_label(university.ranking, university.ranking_label), 'year': None, 'overall': True}
    else:
        subject = {
            'code': pick['code'], 'name': subject_name(pick['code']), 'year': pick['year'], 'overall': False,
            'rank': pick['rank'], 'rank_label': rank_label(pick['rank'], pick['label']) if pick['rank'] is not None else None,
        }
    return {
        'band': entry['band'], 'subject': subject, 'sat': sat_position(university, ctx['sat']),
        'aid_status': entry['status'], 'cost_usd': cost, 'budget_usd': ctx['budget'],
        'cost_vs_budget': budget_position(cost, ctx['budget']), 'cost_unknown': cost is None,
    }


def college_match(profile):
    """The student's list of ten. No AI runs here."""
    return match_with_context(profile)[0]
