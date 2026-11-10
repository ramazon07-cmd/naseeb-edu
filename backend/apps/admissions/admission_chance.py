"""Admission chance: how a student stands at one university, as a band.

College Search keeps two answers apart. Fit (country, major, aid) says whether a
university suits the student and orders the list. Chance says how likely
admission is, as a band:

1. Entry gates (school certificate route, IELTS minimum). Failing one is
   "not eligible", whatever the scores.
2. Academic position against the university's admitted students (SAT/ACT
   25th-75th percentile, or a GPA bar by selectivity). At selective schools
   academics act as a gate: soft strengths count only once academics are near
   the bar (in the SFFA v. Harvard data, admit rates fall from 66% to 0.02%
   across the academic ratings).
3. A grid of the student's weighted position against the admit rate for
   students from abroad (estimated from the overall rate when not published).

No AI runs here: every university is scored with the same rules, once per
profile. Weights and thresholds are starting values to tune with recorded
outcomes (AdmissionChanceSnapshot).
"""
from .models import University

ALGORITHM_VERSION = 'chance-v1'

FAR_REACH, REACH, TARGET, SAFETY = 'far_reach', 'reach', 'target', 'safety'
NOT_ELIGIBLE = 'not_eligible'
# Hardest first: "one step harder" moves left, a cap takes the harder of two bands.
STEPS = (FAR_REACH, REACH, TARGET, SAFETY)
BANDS = (*STEPS, NOT_ELIGIBLE)

# Weights over the four rubric factors per admission model.
WEIGHTS = {
    'holistic_elite': {'academics': 0.40, 'activities': 0.30, 'essays': 0.15, 'recommendations': 0.15},
    'academic_plus_us': {'academics': 0.70, 'activities': 0.15, 'essays': 0.10, 'recommendations': 0.05},
    'academic_plus': {'academics': 0.80, 'activities': 0.05, 'essays': 0.10, 'recommendations': 0.05},
}
# Models where weak academics cancel soft-factor strengths.
GATED_MODELS = {'holistic_elite', 'academic_plus_us'}

POSITION_LIMIT = 1.5
# Academics more than one 25th-75th spread below the 25th percentile: no better than Reach.
# Near the clamp floor: Far reach.
REACH_CAP_ACADEMICS = -1
FAR_REACH_ACADEMICS = -1.4
# Smallest 25th-75th spread used, so a narrow published range does not exaggerate a gap.
MIN_SPREAD = {'SAT': 100, 'ACT': 3}
# Without a published range, the GPA share (GPA / scale) expected at the 25th and 75th percentile
# of admits, by admit rate for students from abroad (upper bounds, ascending).
GPA_BARS = ((15, 0.95, 1.00), (25, 0.90, 0.97), (50, 0.85, 0.95), (101, 0.75, 0.90))
# The activities score (0-10) expected at the 25th percentile, by the same admit rate.
ACTIVITY_BARS = ((10, 8), (25, 7), (50, 6), (75, 5), (101, 3))
ACTIVITY_SPREAD = 2
# Position classes: (lowest position, class), best first.
POSITION_CLASSES = ((0.5, 'strong'), (-0.25, 'mid'), (-0.75, 'low'))
# Band by admit rate (lower bound) and position class.
GRID = (
    (50, {'strong': SAFETY, 'mid': TARGET, 'low': REACH, 'very_low': FAR_REACH}),
    (25, {'strong': TARGET, 'mid': TARGET, 'low': REACH, 'very_low': FAR_REACH}),
    (15, {'strong': TARGET, 'mid': REACH, 'low': REACH, 'very_low': FAR_REACH}),
    (5, {'strong': REACH, 'mid': REACH, 'low': FAR_REACH, 'very_low': FAR_REACH}),
    (0, {'strong': FAR_REACH, 'mid': FAR_REACH, 'low': FAR_REACH, 'very_low': FAR_REACH}),
)
CREDENTIAL_GAPS = {
    University.CredentialRoute.FOUNDATION: ('credential_foundation', 'The Uzbek school certificate needs a foundation year here first'),
    University.CredentialRoute.ONE_YEAR_UNIVERSITY: (
        'credential_one_year', 'The Uzbek school certificate needs one year of university study first',
    ),
    University.CredentialRoute.STUDIENKOLLEG: ('credential_studienkolleg', 'The Uzbek school certificate needs a Studienkolleg year first'),
    University.CredentialRoute.NOT_ACCEPTED: (
        'credential_not_accepted', 'The Uzbek school certificate alone is not accepted; IB, A-levels or a university year may be',
    ),
}
GATE_CODES = {code for code, _ in CREDENTIAL_GAPS.values()} | {'english_below_minimum'}


def clamp(value, low=-POSITION_LIMIT, high=POSITION_LIMIT):
    return max(low, min(high, value))


def harder(band, cap):
    """The harder of ``band`` and ``cap``."""
    return STEPS[min(STEPS.index(band), STEPS.index(cap))]


def international_rate(university):
    """``(rate, estimated)``: the admit rate for students from abroad, or ``(None, False)``.

    Students from abroad compete in a tighter pool (MIT: about 2% against 4.5% overall), so an
    unpublished rate is estimated from the overall one.
    """
    if university.intl_acceptance_rate is not None:
        return float(university.intl_acceptance_rate), False
    if university.acceptance_rate is None:
        return None, False
    rate = float(university.acceptance_rate)
    if rate < 25:
        return rate * 0.5, True
    if rate < 50:
        return rate * 0.8, True
    return rate, False


def admission_model(university):
    is_us = university.market == University.Market.US or University.market_for_country(university.country) == University.Market.US
    if not is_us:
        return 'academic_plus'
    rate = university.acceptance_rate
    return 'holistic_elite' if rate is not None and float(rate) < 25 else 'academic_plus_us'


def by_rate(table, rate):
    return next(row[1:] for row in table if rate < row[0])


def test_position(test, score, low, high):
    spread = max((high or low) - low, MIN_SPREAD[test])
    return clamp((score - low) / spread)


def academic_position(university, ctx, rate):
    """Academics against admitted students: 0 at their 25th percentile, 1 at the 75th.

    ``None`` when the university expects a test the student has no score for: unknown, not low.
    """
    tests = []
    if ctx['sat'] is not None and university.sat_min:
        tests.append(test_position('SAT', ctx['sat'], university.sat_min, university.sat_max))
    if ctx['act'] is not None and university.act_min:
        tests.append(test_position('ACT', ctx['act'], university.act_min, university.act_max))
    low, high = by_rate(GPA_BARS, rate)
    grades = clamp((ctx['gpa'] / ctx['gpa_scale'] - low) / (high - low))
    if tests:
        return 0.6 * max(tests) + 0.4 * grades
    ranges = bool(university.sat_min or university.act_min)
    if ranges and not university.test_optional:
        return None
    return grades


def position_class(position):
    return next((name for low, name in POSITION_CLASSES if position >= low), 'very_low')


def gates(university, ctx):
    """Entry requirements the student fails, as gap items (empty when none fail or none are known).

    Students are taken to hold the Uzbek school certificate; the profile has no other credential yet.
    """
    failed = []
    route = university.credential_route
    if route in CREDENTIAL_GAPS:
        code, text = CREDENTIAL_GAPS[route]
        failed.append({'code': code, 'params': {}, 'text': text})
    english = ctx['english']
    if university.ielts_min is not None and english is not None and english['ielts'] < float(university.ielts_min):
        minimum = float(university.ielts_min)
        failed.append({
            'code': 'english_below_minimum', 'params': {'test': english['test'], 'score': english['score'], 'min': minimum},
            'text': f'{english["test"]} {english["score"]:g} is below the IELTS {minimum:g} minimum',
        })
    return failed


def chance(university, ctx):
    """The band and how it was reached. ``band`` is None when the data cannot place the university."""
    model = admission_model(university)
    rate, estimated = international_rate(university)
    result = {
        'band': None, 'model': model, 'admit_rate': None if rate is None else round(rate, 1),
        'admit_rate_estimated': estimated, 'position': None, 'academic_position': None,
        'gates': [], 'notes': [], 'version': ALGORITHM_VERSION,
    }
    failed = gates(university, ctx)
    if failed:
        result.update(band=NOT_ELIGIBLE, gates=failed)
        return result
    if rate is None:
        return result
    row = next(row for low, row in GRID if rate >= low)
    academics = academic_position(university, ctx, rate)
    if academics is None:
        # Some admit rates give every student the same band, whatever the scores.
        if len(set(row.values())) == 1:
            result['band'] = next(iter(row.values()))
        return result
    weights = WEIGHTS[model]
    gate = clamp(1 + academics, 0, 1) if model in GATED_MODELS else 1
    activity_bar, = by_rate(ACTIVITY_BARS, rate)
    activities = clamp((ctx['strength'] - activity_bar) / ACTIVITY_SPREAD)
    # Essays and recommendations are not scored yet: taken as at the bar (0), neither help nor harm.
    soft = weights['activities'] * (activities if activities < 0 else gate * activities)
    position = weights['academics'] * academics + soft
    band = row[position_class(position)]
    if academics <= FAR_REACH_ACADEMICS:
        band = FAR_REACH
    elif academics < REACH_CAP_ACADEMICS:
        band = harder(band, REACH)
        result['notes'].append({'code': 'academics_below_bar', 'params': {}, 'text': 'Your academics are below most admitted students here'})
    if ctx['scholarship_needed'] and university.intl_need_policy == University.IntlNeedPolicy.NEED_AWARE:
        band = STEPS[max(0, STEPS.index(band) - 1)]
        result['notes'].append({'code': 'need_aware', 'params': {}, 'text': 'Asking for aid lowers the chances at this need-aware university'})
    if university.entrance_exam:
        band = harder(band, TARGET)
        result['notes'].append({
            'code': 'entrance_exam', 'params': {'exam': university.entrance_exam},
            'text': f'Admission also depends on an entrance exam: {university.entrance_exam}',
        })
    result.update(band=band, position=round(position, 2), academic_position=round(academics, 2))
    return result
