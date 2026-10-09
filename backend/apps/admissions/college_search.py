"""College Search: the university catalogue filtered, sorted and paged on the server.

Students open College Search on whatever connection they have, so the page asks
for one small page at a time (10, 25, 50 or 100 universities) instead of the
whole ~1,500-row catalogue: the first rows arrive quickly and the server only
serializes what is shown. Filters, sorting and the facet counts run here, and
every row carries the student's fit for that university.

Scoring the whole catalogue is needed only to sort by fit, to filter by
admission band or to count bands. That map is computed once per student,
profile answers and catalogue version, then cached.
"""
import hashlib
import json

from django.db.models import Case, Count, F, IntegerField, OuterRef, Prefetch, Q, Subquery, When
from django.db.models.functions import Coalesce
from rest_framework import serializers

from apps.users.cache_safety import cache_get, cache_set

from .catalog_cache import CACHE_SECONDS, VERSION_KEY
from .countries import country_key, country_name, country_spellings
from .listing import MAX_SEARCH_LENGTH, search_terms, term_query
from .models import StudentProfile, University, UniversityProgram

PAGE_SIZES = (10, 25, 50, 100)
MAX_IDS = 100
SEARCH_FIELDS = ('name', 'city', 'country')
# A market is listed under one name ('USA' and 'United States' are one country).
MARKET_COUNTRIES = dict(University.Market.choices)
PRICE_CAPS = {'25000': 25000, '40000': 40000}
AID_FLAGS = ('offers_need_based_aid', 'offers_merit_aid', 'offers_international_aid', 'meets_full_need')
OFFERED_AID = ('offers_international_aid', 'offers_merit_aid', 'offers_need_based_aid')
# Any of these means the catalogue row was given aid details (frontend UniversityPage hasAidData);
# without them a QS-only row's false aid flags mean "unknown", not "no aid".
AID_DETAILS = (
    'average_aid_usd', 'students_receiving_aid_percent', 'financial_aid_url', 'scholarship_deadline',
    'aid_application_notes', 'need_blind', 'css_profile_required', 'fafsa_required', 'meets_full_need',
)
AID_AMOUNTS = ('average_aid_usd', 'students_receiving_aid_percent')
BANDS = ('reach', 'target', 'safety')
# A row without admission data has no band; the filter and the facets call it "unknown".
UNKNOWN_BAND = 'unknown'
BAND_CHOICES = (*BANDS, UNKNOWN_BAND)
QS_FILTERS = ('region', 'size', 'focus', 'research')
# What a student from abroad pays per year. A US row's net price is Scorecard's average for
# domestic aid recipients (in-state ones at a public university), so it is only used where the
# university gives international students aid; otherwise the international cost of attendance.
# Rows outside the US keep their own price. ``cost_of_attendance`` is the same rule in Python.
COST = Case(
    When(market=University.Market.US, offers_international_aid=True, net_price_usd__isnull=False, then=F('net_price_usd')),
    When(market=University.Market.US, then=F('intl_cost_usd')),
    default=F('net_price_usd'),
    output_field=IntegerField(),
)
ORDERINGS = {
    'ranking': (F('ranking').asc(nulls_last=True), 'name', 'id'),
    'price': (F('cost').asc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
    'deadline': (F('application_deadline').asc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
    'acceptance': (F('acceptance_rate').desc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
}
SORTS = (*ORDERINGS, 'fit')
# The profile answers scoring needs; College Research asks for the missing ones. Test scores
# are not among them: a factor without a score is left out of the fit, not guessed.
RESEARCH_FIELDS = ('gpa', 'target_major', 'target_countries', 'budget_usd')
EVIDENCE = ('achievements', 'honors', 'researches', 'projects', 'internships', 'activities')
SCORING_FIELDS = (
    'id', 'country', 'market', 'ranking', 'sat_min', 'sat_max', 'act_min', 'act_max', 'popular_majors',
    'net_price_usd', 'intl_cost_usd', 'acceptance_rate', 'test_optional', *OFFERED_AID, *AID_DETAILS,
)
TEST_POINTS = 25
ENGLISH_POINTS = 8
PRICE_POINTS = 12
AID_POINTS = 8
# How far below a range minimum still counts as "close".
NEAR_MINIMUM = {'SAT': 80, 'ACT': 2}
ENGLISH_TESTS = {'toefl': 'TOEFL', 'duolingo': 'Duolingo', 'pte': 'PTE', 'cambridge': 'Cambridge'}
# Lowest score for each IELTS Academic band, highest first, from each test owner's published
# concordance. A score below a table's lowest row is given the band under it.
IELTS_CONCORDANCE = {
    # ETS, "Linking TOEFL iBT Scores to IELTS Scores" (2010).
    'toefl': ((118, 9), (115, 8.5), (110, 8), (102, 7.5), (94, 7), (79, 6.5), (60, 6), (46, 5.5), (35, 5), (32, 4.5), (0, 4)),
    # Duolingo English Test, "Score interpretation: comparison with IELTS Academic" (2019, 991 test takers).
    'duolingo': (
        (155, 9), (145, 8.5), (135, 8), (125, 7.5), (115, 7), (105, 6.5), (95, 6), (85, 5.5), (75, 5),
        (65, 4.5), (55, 4), (45, 3.5), (30, 3), (20, 2.5), (15, 2), (10, 1.5),
    ),
    # Pearson, PTE Academic and IELTS Academic concordance (2024 study, July 2025 report).
    'pte': ((90, 9), (86, 8.5), (79, 8), (71, 7.5), (63, 7), (55, 6.5), (47, 6), (39, 5.5), (31, 5), (24, 4.5), (0, 4)),
    # Cambridge Assessment English, "Comparing scores to IELTS" (B2 First and C1 Advanced): the
    # Cambridge English Scale is published up to IELTS 7.5.
    'cambridge': ((191, 7.5), (185, 7), (176, 6.5), (169, 6), (162, 5.5), (154, 5), (0, 4.5)),
}


def eligible_programs(*fields):
    """Programs a student from abroad can apply to: the only ones scored and listed."""
    programs = UniversityProgram.objects.filter(is_active=True, international_students_eligible=True)
    return Prefetch('programs', queryset=programs.only(*fields) if fields else programs)


# ---------------------------------------------------------------- fit scoring

def evidence_counts(profile):
    """The student's evidence rows per kind, counted in one query."""
    counts = {}
    for name in EVIDENCE:
        relation = StudentProfile._meta.get_field(name)
        owner = relation.field.name
        rows = relation.related_model._default_manager.filter(**{owner: OuterRef('pk')}).order_by().values(owner)
        counts[f'{name}_count'] = Coalesce(Subquery(rows.annotate(total=Count('pk')).values('total'), output_field=IntegerField()), 0)
    row = StudentProfile.objects.filter(pk=profile.pk).values(**counts).get()
    return {name: row[f'{name}_count'] for name in EVIDENCE}


def missing_fields(profile):
    return [field for field in RESEARCH_FIELDS if getattr(profile, field) in (None, '')]


def ielts_equivalent(test, score):
    return next(band for low, band in IELTS_CONCORDANCE[test] if score >= low)


def certificates(profile, *types):
    """The student's scored certificates of ``types`` (onboarding stores standard test scores as ints)."""
    rows = (profile.application_profile or {}).get('certificates') or []
    return [row for row in rows if row.get('type') in types and isinstance(row.get('score'), int)]


def best_english(profile):
    """The student's strongest English result as its IELTS equivalent, or None without one."""
    results = []
    if profile.ielts_score is not None:
        score = float(profile.ielts_score)
        results.append({'test': 'IELTS', 'score': score, 'ielts': score})
    for row in certificates(profile, *ENGLISH_TESTS):
        results.append({'test': ENGLISH_TESTS[row['type']], 'score': row['score'], 'ielts': ielts_equivalent(row['type'], row['score'])})
    return max(results, key=lambda result: result['ielts'], default=None)


def fit_context(profile):
    """What scoring reads from a profile, or None while research answers are missing.

    Everything scoring reads is here, because it is also the fit cache key.
    """
    if missing_fields(profile):
        return None
    counts = evidence_counts(profile)
    act = [row['score'] for row in certificates(profile, 'act')]
    return {
        'gpa': float(profile.gpa),
        'gpa_scale': int(profile.effective_gpa_scale),
        'sat': int(profile.sat_score) if profile.sat_score is not None else None,
        'sat_status': profile.sat_status,
        'act': max(act, default=None),
        'english': best_english(profile),
        'budget': int(profile.budget_usd),
        'countries': sorted({country_key(value) for value in profile.target_countries.split(',') if value.strip()}),
        'major': profile.target_major.strip().lower(),
        'major_name': profile.target_major,
        'scholarship_needed': bool(profile.scholarship_needed),
        'strength': min(10, sum(min(value, 2) for value in counts.values()) * 2),
    }


def item(code, text, **params):
    """One reason or gap: a code and params the frontend translates, and the English text."""
    return {'code': code, 'params': params, 'text': text}


def cost_of_attendance(university):
    """``(yearly cost or None, after_aid)``: the Python side of ``COST``."""
    if university.market == University.Market.US:
        if university.offers_international_aid and university.net_price_usd is not None:
            return university.net_price_usd, True
        return university.intl_cost_usd, False
    return university.net_price_usd, False


def has_aid_data(university):
    """Whether the catalogue says anything about this university's aid (see ``AID_DETAILS``)."""
    if any(getattr(university, name) for name in OFFERED_AID):
        return True
    return any(
        getattr(university, name) is not None if name in AID_AMOUNTS else bool(getattr(university, name))
        for name in AID_DETAILS
    )


def range_fit(test, score, low, high):
    """``(points, is_reason, item, below_minimum)`` for one test score against a catalogue range."""
    high = high or low
    key = test.lower()
    if score >= high:
        return 25, True, item(f'{key}_above_range', f'{test} {score} meets or exceeds the catalog range', score=score), False
    if score >= low:
        return 22, True, item(f'{key}_in_range', f'{test} {score} fits the {low}–{high} catalog range', score=score, min=low, max=high), False
    if score >= low - NEAR_MINIMUM[test]:
        return 12, False, item(f'{key}_near_minimum', f'{test} is {low - score} points below the catalog minimum', points=low - score, min=low), True
    return 4, False, item(f'{key}_below_minimum', f'Raise {test} toward at least {low}', min=low), True


def score_university(university, ctx):
    """One university's fit for a ready profile. ``university.programs`` must be the eligible ones."""
    reasons = []
    gaps = []
    # Points of factors with no data (the catalogue's or the student's): they are left out, not guessed.
    missing = 0

    academic = round(min(15, (ctx['gpa'] / ctx['gpa_scale']) * 15))
    tests = []
    if ctx['sat'] is not None and university.sat_min:
        tests.append(range_fit('SAT', ctx['sat'], university.sat_min, university.sat_max))
    if ctx['act'] is not None and university.act_min:
        tests.append(range_fit('ACT', ctx['act'], university.act_min, university.act_max))
    taken = [name for name, score in (('SAT', ctx['sat']), ('ACT', ctx['act'])) if score is not None]
    ranges = bool(university.sat_min or university.act_min)
    not_required = ctx['sat_status'] == StudentProfile.TestStatus.NOT_REQUIRED
    below = False
    if tests:
        points, is_reason, note, below = max(tests, key=lambda result: result[0])
        academic += points
        (reasons if is_reason else gaps).append(note)
    elif university.test_optional:
        reasons.append(item('tests_optional', 'SAT and ACT are optional at this university'))
        if taken or not_required:
            academic += 20
        else:
            missing += TEST_POINTS
    elif ranges and not taken and not_required:
        academic += 4
        gaps.append(item('tests_required', 'This university expects an SAT or ACT score'))
    elif ranges and not taken:
        missing += TEST_POINTS
        gaps.append(item('test_score_missing', 'Add an SAT or ACT score to compare with admitted students'))
    elif ranges:
        missing += TEST_POINTS
        gaps.append(item('test_range_missing_for', f'The {taken[0]} range is not listed in the catalog', test=taken[0]))
    else:
        missing += TEST_POINTS
        gaps.append(item('test_range_missing', 'SAT and ACT ranges are not listed in the catalog'))

    english = ctx['english']
    if english is None:
        missing += ENGLISH_POINTS
        gaps.append(item('english_missing', 'Add an English test score (IELTS, TOEFL, Duolingo, PTE or Cambridge)'))
    else:
        test, score = english['test'], english['score']
        if english['ielts'] >= 7:
            academic += 8
            reasons.append(item('english_strong', f'{test} {score:g} is a strong language score', test=test, score=score))
        elif english['ielts'] >= 6.5:
            academic += 6
            reasons.append(item('english_suitable', f'{test} {score:g} is suitable for many programs', test=test, score=score))
        else:
            academic += 3
            gaps.append(item('english_check', 'Verify the English test requirement on the official program page', test=test, score=score))

    if country_key(university.country) in ctx['countries']:
        preferences = 12
        reasons.append(item('country_match', f'{university.country} is one of your target countries', country=university.country))
    else:
        preferences = 3
    majors = [program.canonical_major.strip().lower() for program in university.programs.all()]
    majors.extend(value.strip().lower() for value in university.popular_majors.split(',') if value.strip())
    major = ctx['major']
    if major and any(major in name or name in major for name in majors):
        preferences += 10
        reasons.append(item('major_match', f'{ctx["major_name"]} matches an available field of study', major=ctx['major_name']))
    else:
        preferences += 4
        gaps.append(item('major_check', 'Check the exact program requirements for your selected major'))

    budget = ctx['budget']
    cost, after_aid = cost_of_attendance(university)
    if cost is not None:
        prefix, label = ('net_after_aid', 'Estimated net price after aid') if after_aid else (
            'cost', 'Estimated cost of attendance for international students')
        if cost <= budget:
            financial = 12
            reasons.append(item(f'{prefix}_within_budget', f'{label} is within your budget', cost=cost, budget=budget))
        elif cost <= budget * 1.5:
            financial = 7
            gaps.append(item(f'{prefix}_above_budget', f'{label} is above your budget', cost=cost, budget=budget))
        else:
            financial = 2
            gaps.append(item(f'{prefix}_far_above_budget', f'{label} is significantly above your budget', cost=cost, budget=budget))
    else:
        financial = 0
        missing += PRICE_POINTS
        gaps.append(item('cost_missing', 'Estimated cost of attendance for international students is not available in the catalog'))
    if ctx['scholarship_needed']:
        if any(getattr(university, name) for name in OFFERED_AID):
            financial += 8
            reasons.append(item('aid_available', 'A suitable type of financial aid is available'))
        elif has_aid_data(university):
            financial += 1
            gaps.append(item('aid_not_offered', 'The catalog lists no international, merit or need-based aid at this university'))
        else:
            missing += AID_POINTS
            gaps.append(item('aid_unknown', 'Financial aid details are not listed in the catalog'))
    else:
        financial += 8

    earned = academic + preferences + financial + ctx['strength']
    # Score the known factors on the full scale, then take off half the missing weight:
    # a row without admissions data never outscores the same row with data that fits.
    total = min(100, round(earned * 100 / (100 - missing) * (1 - missing / 200)))
    rate = float(university.acceptance_rate) if university.acceptance_rate is not None else None
    if rate is None and not ranges:
        # No admission data in the catalogue (e.g. a QS-only row): unknown, not "target".
        band = None
    elif (rate is not None and rate < 15) or below:
        band = 'reach'
    elif rate is not None and rate >= 45:
        band = 'safety'
    else:
        band = 'target'
    return {
        'match_score': total,
        'match_label': 'Strong match' if total >= 80 else 'Good match' if total >= 65 else 'Developing match',
        'admission_band': band,
        'score_breakdown': {
            'academic': academic,
            'preferences': preferences,
            'financial': financial,
            'profile_strength': ctx['strength'],
        },
        'reasons': reasons[:5],
        'gaps': gaps[:4],
    }


def fit_key(profile, ctx):
    """Cache key prefix for one student's answers on one catalogue version."""
    signature = hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()[:20]
    return f'{profile.pk}:{cache_get(VERSION_KEY, 0)}:{signature}'


def fit_scores(profile, ctx):
    """``{university_id: (score, band)}`` for the whole catalogue.

    The same scores the rows show, so fit sorting, band filters and band counts
    agree with every row. Cached per student, profile answers and catalogue
    version, so paging, re-sorting and refiltering never rescore.
    """
    key = f'college-fit:{fit_key(profile, ctx)}'
    scores = cache_get(key)
    if scores is None:
        universities = University.objects.only(*SCORING_FIELDS).prefetch_related(
            eligible_programs('id', 'university_id', 'canonical_major'),
        )
        scores = {}
        for university in universities:
            fit = score_university(university, ctx)
            scores[university.pk] = (fit['match_score'], fit['admission_band'])
        cache_set(key, scores, CACHE_SECONDS)
    return scores


# ---------------------------------------------------------------- filters and facets

def display_country(market, country):
    return MARKET_COUNTRIES.get(market) or country_name(country)


def country_q(name):
    # 'USA', 'US', 'China (Mainland)' or 'Hong Kong SAR' name the same market as its label.
    market = University.market_for_country(name)
    spellings = Q()
    for spelling in country_spellings(name):
        spellings |= Q(country__iexact=spelling)
    same_name = Q(market='') & spellings
    return Q(market=market) | same_name if market else same_name


def sat_fit_q(sat):
    """In range: a known SAT minimum the student meets, or a test-optional university without one."""
    no_minimum = Q(sat_min__isnull=True) | Q(sat_min=0)
    return Q(sat_min__gt=0, sat_min__lte=sat or 0) | (no_minimum & Q(test_optional=True))


def catalog_facets():
    """Counts over the whole catalogue (the filters do not change them), cached per catalogue version."""
    key = f'college-facets-v2:{cache_get(VERSION_KEY, 0)}'
    facets = cache_get(key)
    if facets is None:
        facets = {
            'total': 0, 'countries': {}, 'aid': dict.fromkeys(AID_FLAGS, 0), 'test_optional': 0, 'public': 0,
            'qs': {name: {} for name in QS_FILTERS},
        }
        rows = University.objects.values_list(
            'market', 'country', 'test_optional', 'institution_type', *AID_FLAGS,
            *(f'qs_data__{name}' for name in QS_FILTERS),
        )
        for market, country, test_optional, institution_type, *values in rows:
            facets['total'] += 1
            name = display_country(market, country)
            if name:
                facets['countries'][name] = facets['countries'].get(name, 0) + 1
            for flag, value in zip(AID_FLAGS, values):
                facets['aid'][flag] += bool(value)
            facets['test_optional'] += bool(test_optional)
            facets['public'] += institution_type == University.InstitutionType.PUBLIC
            for group, value in zip(QS_FILTERS, values[len(AID_FLAGS):]):
                if isinstance(value, str) and value:
                    facets['qs'][group][value] = facets['qs'][group].get(value, 0) + 1
        cache_set(key, facets, CACHE_SECONDS)
    return facets


def student_facets(profile, scores):
    """The catalogue counts plus the two that depend on the student: SAT in range and bands.

    ``unknown`` counts the rows without a band: all of them until the profile is ready.
    """
    catalog = catalog_facets()
    bands = dict.fromkeys(BANDS, 0)
    for _, band in scores.values():
        if band:
            bands[band] += 1
    bands[UNKNOWN_BAND] = catalog['total'] - sum(bands.values())
    sat_fit = University.objects.filter(sat_fit_q(profile.sat_score)).count()
    return {**catalog, 'sat_fit': sat_fit, 'bands': bands}


class CollegeSearchParams(serializers.Serializer):
    """The query string of ``GET /api/college-search/``; anything unknown is a 400."""

    search = serializers.CharField(required=False, allow_blank=True, default='', max_length=MAX_SEARCH_LENGTH)
    country = serializers.CharField(required=False, allow_blank=True, default='', max_length=120)
    price = serializers.ChoiceField(choices=('all', 'budget', *PRICE_CAPS), default='all')
    aid = serializers.CharField(required=False, allow_blank=True, default='')
    # Absent: every band. Present but empty: no band at all (every box unticked).
    # 'unknown' is the rows without a band, so unticking a known band never hides them.
    bands = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    test_optional = serializers.BooleanField(default=False)
    sat_fit = serializers.BooleanField(default=False)
    public = serializers.BooleanField(default=False)
    region = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    size = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    focus = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    research = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    sort = serializers.ChoiceField(choices=SORTS, default='ranking')
    page = serializers.IntegerField(min_value=1, max_value=1000, default=1)
    page_size = serializers.ChoiceField(
        choices=PAGE_SIZES, default=PAGE_SIZES[0], error_messages={'invalid_choice': 'Choose 10, 25, 50 or 100.'},
    )
    ids = serializers.CharField(required=False, allow_blank=True, default='')
    facets = serializers.BooleanField(default=False)

    def to_internal_value(self, data):
        # ``bands`` may come comma-separated or repeated (bands=reach&bands=unknown).
        if hasattr(data, 'getlist') and len(data.getlist('bands')) > 1:
            data = data.copy()
            data['bands'] = ','.join(data.getlist('bands'))
        return super().to_internal_value(data)

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({name: 'Unknown parameter.' for name in unknown})
        return attrs

    @staticmethod
    def _subset(value, allowed, message):
        items = list(dict.fromkeys(item for item in (value or '').split(',') if item))
        if any(item not in allowed for item in items):
            raise serializers.ValidationError(message)
        return items

    def validate_search(self, value):
        return ' '.join(search_terms(value))

    def validate_aid(self, value):
        return self._subset(value, AID_FLAGS, 'Unknown financial aid filter.')

    def validate_bands(self, value):
        return None if value is None else self._subset(value, BAND_CHOICES, 'Choose reach, target, safety or unknown.')

    def validate_ids(self, value):
        try:
            ids = list(dict.fromkeys(int(item) for item in (value or '').split(',') if item.strip()))
        except ValueError:
            raise serializers.ValidationError('Use comma-separated university ids.')
        if len(ids) > MAX_IDS:
            raise serializers.ValidationError(f'Ask for at most {MAX_IDS} universities at a time.')
        return ids


def filtered_catalog(params, profile):
    queryset = University.objects.annotate(cost=COST)
    for term in params['search'].split():
        queryset = queryset.filter(term_query(SEARCH_FIELDS, term))
    if params['country']:
        queryset = queryset.filter(country_q(params['country']))
    # A row without a known cost stays: no published price is not "too expensive". "Within
    # budget" without a budget in the profile has no cap; the page asks for the budget instead.
    cap = profile.budget_usd if params['price'] == 'budget' else PRICE_CAPS.get(params['price'])
    if cap:
        queryset = queryset.filter(Q(cost__isnull=True) | Q(cost__lte=cap))
    for flag in params['aid']:
        queryset = queryset.filter(**{flag: True})
    if params['test_optional']:
        queryset = queryset.filter(test_optional=True)
    if params['sat_fit']:
        queryset = queryset.filter(sat_fit_q(profile.sat_score))
    if params['public']:
        queryset = queryset.filter(institution_type=University.InstitutionType.PUBLIC)
    for name in QS_FILTERS:
        if params[name]:
            queryset = queryset.filter(**{f'qs_data__{name}': params[name]})
    return queryset


def serialize_rows(universities, ctx):
    """Slim rows plus what College Search needs on top: the eligible programs
    (``addToList`` picks one by the target major) and the student's fit."""
    from .serializers import UniversityRowSerializer

    rows = UniversityRowSerializer(universities, many=True).data
    for row, university in zip(rows, universities):
        row['programs'] = [{'name': program.name, 'canonical_major': program.canonical_major} for program in university.programs.all()]
        if ctx is not None:
            row['fit'] = score_university(university, ctx)
    return rows


# The query parameters that change which rows match (not the page or the extras).
FILTER_PARAMS = ('search', 'country', 'price', 'aid', 'bands', 'test_optional', 'sat_fit', 'public', *QS_FILTERS)


def fit_ranking(profile, ctx, params, queryset, scores):
    """The ids matching ``params`` best fit first, cached next to the fit map so
    "Show more" and the background prefetch do not reload and sort the catalogue."""
    filters = json.dumps({name: params[name] for name in FILTER_PARAMS}, sort_keys=True)
    key = f'college-fit-ranked:{fit_key(profile, ctx)}:{hashlib.sha256(filters.encode()).hexdigest()[:20]}'
    ranked = cache_get(key)
    if ranked is None:
        rows = sorted(queryset.values_list('pk', 'ranking'), key=lambda row: (-scores.get(row[0], (-1,))[0], row[1] or 999999))
        ranked = [pk for pk, _ in rows]
        cache_set(key, ranked, CACHE_SECONDS)
    return ranked


def college_search(profile, params):
    """One page of College Search for ``profile`` (validated ``CollegeSearchParams``).

    The fit context (one query for the evidence counts) is read only when the answer
    needs fit: rows to score, fit sorting, a band filter or the band facets.
    """
    ready = not missing_fields(profile)
    rows = University.objects.prefetch_related(eligible_programs())
    if params['ids']:
        # Rows the page already knows by id (the student's list, a university page).
        page = list(rows.filter(pk__in=params['ids']).order_by(*ORDERINGS['ranking']))
        return {'results': serialize_rows(page, fit_context(profile) if ready and page else None)}

    bands = params['bands']
    band_filter = bands is not None and set(bands) != set(BAND_CHOICES)
    by_fit = params['sort'] == 'fit' and ready
    ctx = fit_context(profile) if ready and (by_fit or band_filter or params['facets']) else None
    scores = fit_scores(profile, ctx) if ctx is not None else {}
    queryset = filtered_catalog(params, profile)
    if band_filter:
        if ctx is None:
            # Without a ready profile no row has a band.
            queryset = queryset if UNKNOWN_BAND in bands else queryset.none()
        else:
            wanted = {None if band == UNKNOWN_BAND else band for band in bands}
            queryset = queryset.filter(pk__in=[pk for pk, (_, band) in scores.items() if band in wanted])

    size = params['page_size']
    start = (params['page'] - 1) * size
    if by_fit:
        ranked = fit_ranking(profile, ctx, params, queryset, scores)
        count = len(ranked)
        page_ids = ranked[start:start + size]
        found = {university.pk: university for university in rows.filter(pk__in=page_ids)}
        page = [found[pk] for pk in page_ids if pk in found]
    else:
        # Sorting by fit needs a ready profile; until then the catalogue keeps its ranking order.
        queryset = queryset.order_by(*ORDERINGS.get(params['sort'], ORDERINGS['ranking']))
        count = queryset.count()
        page = list(queryset.prefetch_related(eligible_programs())[start:start + size])
    if ctx is None and ready and page:
        ctx = fit_context(profile)
    data = {
        'count': count,
        'page': params['page'],
        'page_size': size,
        'next': params['page'] + 1 if start + size < count else None,
        'results': serialize_rows(page, ctx),
        # Matching rows without a known cost: kept by the price filter, sorted last by price.
        'unpriced_count': queryset.filter(cost__isnull=True).count(),
    }
    if params['facets']:
        data['facets'] = student_facets(profile, scores)
    return data
