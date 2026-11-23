"""The college match: ten universities for the student's major, chosen by fixed rules (no AI).

The same profile always gives the same list. Every step is a rule over catalogue data:

1. The student's target major (free text) maps to QS subjects (subjects.py). With none mapped the
   overall QS rank is used and the student is told to pick a major.
2. Candidates are the universities with a QS 2026 subject rank in any of those subjects, in the
   student's target countries. Universities without a subject rank whose popular majors name the
   major may follow the ranked ones.
3. Aid and cost gates (``passes_gate``) drop universities a student who needs money cannot afford,
   including ones whose official minimum yearly cost after aid is above the student's budget.
4. The chance band comes from admission_chance.chance with the academics score only: activities and
   essays are neutral there, so they never change who is listed or the band.
5. Within a band: subject rank, then whether the student can afford it (the least they must still pay after
   the largest published aid, ``intl_min_student_pays_usd``, against their budget), then aid for international
   students, then the international admit rate
   (admission_chance.international_rate, the same rate the band uses), then overall QS rank, then name.
6. Three reach (reach, then at most one far reach), four target and three safety universities. A short
   band is filled from the nearest band and the response says so.
"""
import re

from django.db.models import Max

from . import admission_chance
from .college_search import SCORING_FIELDS, country_match, eligible_programs, fit_context, has_aid_data, serialize_rows
from .models import University, UniversitySubjectRank
from .pricing import with_cost
from .subjects import SUBJECTS, split_majors_whole, subject_name, subjects_for_major

# (group, how many, the bands it takes first-to-last).
MATCH_GROUPS = (
    ('reach', 3, (admission_chance.REACH, admission_chance.FAR_REACH)),
    ('target', 4, (admission_chance.TARGET,)),
    ('safety', 3, (admission_chance.SAFETY,)),
)
# Where a short group takes its missing universities from, nearest first.
FILL_ORDER = {'reach': ('target', 'safety'), 'target': ('reach', 'safety'), 'safety': ('target', 'reach')}
# The reach group takes at most this many far-reach universities; the rest of a short reach group comes from
# target, then safety, before a second far reach.
MAX_FAR_REACH = 1
MATCH_PROGRAMS = 2
COST_CAP_FACTOR = 2
AID_ORDER = {'yes': 0, 'need_aware': 1, 'limited': 2, 'merit': 3, 'none': 4, 'unknown': 5}
NO_RANK = 10 ** 9
AID_FIELDS = (
    'intl_aid_availability', 'intl_max_award_usd', 'intl_min_student_pays_usd', 'financial_aid_url',
    'aid_verified_at', 'aid_academic_year', 'intl_merit_based', 'intl_need_based', 'intl_full_ride',
)
MATCH_FIELDS = (*SCORING_FIELDS, *AID_FIELDS, 'name', 'ranking_label', 'tuition_usd')


def aid_status(university):
    """What the catalogue says about aid for a student from abroad: yes, limited, need_aware, merit, none or unknown.

    An official answer (``intl_aid_availability``: yes, limited, no) wins; "unknown" falls back to the older flags.
    """
    availability = university.intl_aid_availability
    if availability == University.IntlAidAvailability.NO:
        return 'none'
    if availability == University.IntlAidAvailability.LIMITED:
        return 'limited'
    policy = university.intl_need_policy
    if policy == University.IntlNeedPolicy.NEED_BLIND or (
        university.offers_international_aid and (university.meets_full_need or university.need_blind)
    ):
        return 'yes'
    if availability == University.IntlAidAvailability.YES:
        return 'yes'
    if policy == University.IntlNeedPolicy.NEED_AWARE:
        return 'need_aware'
    if university.offers_international_aid:
        return 'yes'
    if university.offers_merit_aid:
        return 'merit'
    return 'none' if has_aid_data(university) else 'unknown'


def gives_international_aid(university):
    availability = university.intl_aid_availability
    if availability in (University.IntlAidAvailability.YES, University.IntlAidAvailability.LIMITED):
        return True
    if availability == University.IntlAidAvailability.NO:
        return False
    return bool(university.offers_international_aid or university.intl_need_policy)


def is_us(university):
    """A US university, by its market or, when the market is blank, by its country."""
    us = University.Market.US
    return university.market == us or University.market_for_country(university.country) == us


def international_cost(university):
    """What a student from abroad pays per year.

    * US (by market or country): ``intl_cost_usd`` only. A US net price is what US students pay after aid,
      so a US row without an international cost stays unpriced.
    * Elsewhere: the net price (``cost`` from pricing.py), then ``tuition_usd``.
    """
    if is_us(university):
        return university.intl_cost_usd
    cost = getattr(university, 'cost', university.net_price_usd)
    return cost if cost is not None else university.tuition_usd


def min_student_pays(university):
    """The least a student must still pay per year after the largest published aid, in USD; None when unknown."""
    return university.intl_min_student_pays_usd


def affordable_with_aid(university, budget):
    """True/False: the official minimum after aid is within/above the budget. None: unknown (never "no")."""
    pays = min_student_pays(university)
    if pays is None or budget is None:
        return None
    return pays <= budget


def affordability_tier(university, budget):
    """0 affordable with aid (official numbers), 1 unknown, 2 still over the budget after the largest aid."""
    result = affordable_with_aid(university, budget)
    return 1 if result is None else 0 if result else 2


def passes_gate(university, cost, ctx):
    """The aid and cost gate for a student's budget.

    * Needs a scholarship and the university gives none to students from abroad: kept only when it
      is known to cost no more than the budget (an unknown cost or budget drops it).
    * Costs more than twice the budget and gives no aid to students from abroad: dropped.
    * Needs a scholarship and even the largest published aid leaves more than the budget to pay: dropped
      (``affordable_with_aid`` is None, unknown, when the official numbers are missing, and then it stays).
    """
    budget = ctx['budget']
    if ctx['scholarship_needed'] and affordable_with_aid(university, budget) is False:
        return False
    if gives_international_aid(university):
        return True
    if ctx['scholarship_needed'] and (cost is None or budget is None or cost > budget):
        return False
    return not (cost is not None and budget is not None and cost > COST_CAP_FACTOR * budget)


def sat_position(university, sat, act=None):
    """The student's SAT against the university's published range: below, inside or above, with the numbers.

    No SAT but an ACT, at a university with a test range: ``act_used`` with the ACT score (the band compared it).
    """
    low, high = university.sat_min, university.sat_max
    if sat is None and act is not None and (low or university.act_min):
        return {'position': 'act_used', 'score': act, 'min': low, 'max': high}
    if not low:
        return {'position': 'no_range', 'score': sat, 'min': None, 'max': None}
    if sat is None:
        return {'position': 'no_score', 'score': None, 'min': low, 'max': high}
    position = 'below' if sat < low else 'above' if high and sat > high else 'inside'
    return {'position': position, 'score': sat, 'min': low, 'max': high}


def budget_position(cost, budget, min_pays=None):
    """within; within_with_aid (costs more than the budget but the largest published aid brings it inside); over."""
    if cost is None:
        return 'unknown' if min_pays is None or budget is None else ('within_with_aid' if min_pays <= budget else 'over')
    if budget is None:
        return 'no_budget'
    if cost <= budget:
        return 'within'
    return 'within_with_aid' if min_pays is not None and min_pays <= budget else 'over'


def rank_label(rank, label):
    return label.lstrip('=') if label else str(rank)


def covers(student_code, program_code):
    """A program subject answers a student's subject when equal, or when the student named a broad area."""
    return student_code == program_code or (student_code.startswith('AREA_') and SUBJECTS[program_code][1] == student_code)


def names(text, major):
    """True when ``major`` appears in ``text`` as whole words, so 'cs' is not found inside 'physics'."""
    return bool(major) and re.search(r'(?<!\w)' + re.escape(major) + r'(?!\w)', text) is not None


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
            if names(name, major) or names(major, name) or any(covers(mine, other) for mine in wanted for other in theirs):
                found.append({'name': program.name, 'canonical_major': program.canonical_major})
    return found[:MATCH_PROGRAMS]


def intended_majors(profile):
    """The stated majors, with compound names ("Oil and gas") kept whole."""
    return split_majors_whole(profile.target_major)


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
            if hits or any(names(popular.lower(), major) for major in majors):
                picks[pk] = {'code': (hits or subject_codes)[0], 'rank': None, 'label': '', 'score': None, 'year': None}
    # Target countries, as College Search reads them ('Europe' also matches the QS region).
    meta = University.objects.filter(pk__in=list(picks)).values_list('pk', 'country', 'qs_data__region')
    allowed = {pk for pk, country, region in meta if country_match(_Place(country, region), countries)}
    return {pk: pick for pk, pick in picks.items() if pk in allowed}


class _Place:
    """The two facts ``country_match`` reads, without loading the whole university row."""

    def __init__(self, country, region):
        self.country, self.qs_data = country, {'region': region}


def sort_key(university, pick, status, budget=None):
    rate = admission_chance.international_rate(university)[0]
    return (
        pick['rank'] if pick['rank'] is not None else NO_RANK,
        affordability_tier(university, budget),
        AID_ORDER[status],
        0 if rate is not None else 1, -(rate or 0),
        university.ranking or NO_RANK,
        university.name.lower(), university.pk,
    )


def by_band(entries, band):
    return sorted((entry for entry in entries if entry['band'] == band), key=lambda entry: entry['key'])


def pick_list(entries):
    """``(groups, notes)``: 3 reach, 4 target, 3 safety; a short group is filled from the nearest group.

    Reach takes reach entries first and at most MAX_FAR_REACH far-reach ones. Still short, it fills from
    target, then safety, and only then takes another far reach. Far-reach entries never fill other groups.
    """
    reach, far = by_band(entries, admission_chance.REACH), by_band(entries, admission_chance.FAR_REACH)
    pools = {
        'reach': reach + far[:MAX_FAR_REACH],
        'target': by_band(entries, admission_chance.TARGET),
        'safety': by_band(entries, admission_chance.SAFETY),
    }
    extra_far = far[MAX_FAR_REACH:]
    chosen = {group: pools[group][:quota] for group, quota, _ in MATCH_GROUPS}
    spare = {group: [entry for entry in pools[group][quota:] if entry['band'] != admission_chance.FAR_REACH]
             for group, quota, _ in MATCH_GROUPS}
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
                'text': f'Too few universities in the {group} group fit you; {len(taken)} from the {donor} group were added.',
            })
        if group == 'reach':
            missing = quota - len(chosen[group])
            chosen[group] += extra_far[:max(missing, 0)]
    total = sum(len(rows) for rows in chosen.values())
    if total < sum(quota for _, quota, _ in MATCH_GROUPS):
        notes.append({'code': 'short_list', 'params': {'count': total}, 'text': f'Only {total} universities fit your profile and budget.'})
    return chosen, notes


def left_out_notes(counts):
    """The notes for universities the rules left out, in a fixed order."""
    texts = {
        'test_needed': '{n} universities were left out because they expect an SAT or ACT score; add yours to see them',
        'aid_unknown': '{n} universities were left out: the catalogue has no aid details',
        'no_intl_aid': '{n} universities were left out: they list no aid for students from abroad',
        'over_budget_with_aid': '{n} universities were left out: even with the largest aid they publish, you would pay more than your budget',
        'no_admission_data': '{n} universities were left out because the catalogue has no admission data to place them',
    }
    return [{'code': code, 'params': {'count': counts[code]}, 'text': text.format(n=counts[code])}
            for code, text in texts.items() if counts[code]]


def match_with_context(profile):
    """``(match, ctx)``: the list of ten and the fit context it was built from."""
    ctx = fit_context(profile)
    subject_codes = subjects_for_major(profile.target_major)
    ctx['budget'] = profile.budget_usd
    # The same context College Search, the university page and the saved snapshot use, so a band never changes between them.
    chance_ctx = ctx
    majors = intended_majors(profile)
    picks = candidates(subject_codes, majors, ctx)
    universities = with_cost(University.objects.only(*MATCH_FIELDS)).filter(pk__in=list(picks))
    entries = []
    left_out = dict.fromkeys(('test_needed', 'aid_unknown', 'no_intl_aid', 'over_budget_with_aid', 'no_admission_data'), 0)
    no_test = ctx['sat'] is None and ctx['act'] is None
    for university in universities:
        cost = international_cost(university)
        if not passes_gate(university, cost, ctx):
            if ctx['scholarship_needed']:
                if affordable_with_aid(university, ctx['budget']) is False:
                    left_out['over_budget_with_aid'] += 1
                else:
                    left_out['aid_unknown' if aid_status(university) == 'unknown' else 'no_intl_aid'] += 1
            continue
        band = admission_chance.chance(university, chance_ctx)['band']
        if band not in admission_chance.STEPS:
            if band is None:
                needs_test = no_test and bool(university.sat_min or university.act_min)
                left_out['test_needed' if needs_test else 'no_admission_data'] += 1
            continue
        status = aid_status(university)
        pick = picks[university.pk]
        entries.append({
            'id': university.pk, 'band': band, 'pick': pick, 'status': status, 'cost': cost,
            'key': sort_key(university, pick, status, ctx['budget']),
        })
    chosen, notes = pick_list(entries)
    notes += left_out_notes(left_out)
    ids = [entry['id'] for rows in chosen.values() for entry in rows]
    full = list(with_cost(University.objects.prefetch_related(eligible_programs())).filter(pk__in=ids))
    serialized = {row['id']: row for row in serialize_rows(full, chance_ctx)}
    programs = {university.pk: suggested_programs(university, majors) for university in full}
    by_pk = {university.pk: university for university in full}
    for rows in chosen.values():
        for entry in rows:
            row = serialized[entry['id']]
            row['suggested_programs'] = programs[entry['id']]
            row.update(card_facts(by_pk[entry['id']], entry, ctx))
            add_aid_budget_note(row['fit'], by_pk[entry['id']], ctx['budget'])
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


def aid_facts(university):
    """The official international-aid facts for a card; every number is None when the official site gave none."""
    availability = university.intl_aid_availability
    return {
        'availability': availability if availability in ('yes', 'limited', 'no') else 'unknown',
        'max_award_usd': university.intl_max_award_usd,
        'min_student_pays_usd': university.intl_min_student_pays_usd,
        'merit': university.intl_merit_based, 'need_based': university.intl_need_based,
        'full_ride': university.intl_full_ride,
        'source_url': university.financial_aid_url or None,
        'academic_year': university.aid_academic_year or None,
        'verified_at': university.aid_verified_at.isoformat() if university.aid_verified_at else None,
    }


def add_aid_budget_note(fit, university, budget):
    """Put the student's budget against the official minimum cost after aid first in the card's reasons or gaps."""
    pays = min_student_pays(university)
    if pays is None or budget is None:
        return
    params = {'pays': pays, 'budget': budget}
    if pays <= budget:
        text = f'With the largest published aid you would pay at least ${pays:,} a year, within your budget of ${budget:,}'
        fit['reasons'] = [note_item('aid_fits_budget', text, params), *fit['reasons']][:5]
    else:
        text = f'Even with the largest published aid you would pay at least ${pays:,} a year, above your budget of ${budget:,}'
        fit['gaps'] = [note_item('aid_over_budget', text, params), *fit['gaps']][:4]


def note_item(code, text, params):
    return {'code': code, 'params': params, 'text': text}


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
        'band': entry['band'], 'subject': subject, 'sat': sat_position(university, ctx['sat'], ctx.get('act')),
        'aid_status': entry['status'], 'cost_usd': cost, 'budget_usd': ctx['budget'],
        'cost_vs_budget': budget_position(cost, ctx['budget'], min_student_pays(university)), 'cost_unknown': cost is None,
        'aid': aid_facts(university),
    }


def college_match(profile):
    """The student's list of ten. No AI runs here."""
    return match_with_context(profile)[0]
