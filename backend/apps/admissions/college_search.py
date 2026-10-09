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

from django.db.models import F, Prefetch, Q
from rest_framework import serializers

from apps.users.cache_safety import cache_get, cache_set

from .catalog_cache import CACHE_SECONDS, VERSION_KEY
from .countries import country_key, country_name, country_spellings
from .listing import MAX_SEARCH_LENGTH, search_terms, term_query
from .models import University, UniversityProgram

PAGE_SIZES = (10, 25, 50, 100)
MAX_IDS = 100
SEARCH_FIELDS = ('name', 'city', 'country')
# A market is listed under one name ('USA' and 'United States' are one country).
MARKET_COUNTRIES = {'us': 'United States', 'canada': 'Canada', 'china': 'China', 'hong_kong': 'Hong Kong'}
PRICE_CAPS = {'25000': 25000, '40000': 40000}
AID_FLAGS = ('offers_need_based_aid', 'offers_merit_aid', 'offers_international_aid', 'meets_full_need')
BANDS = ('reach', 'target', 'safety')
QS_FILTERS = ('region', 'size', 'focus', 'research')
ORDERINGS = {
    'ranking': (F('ranking').asc(nulls_last=True), 'name', 'id'),
    'price': (F('net_price_usd').asc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
    'deadline': (F('application_deadline').asc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
    'acceptance': (F('acceptance_rate').desc(nulls_last=True), F('ranking').asc(nulls_last=True), 'id'),
}
SORTS = (*ORDERINGS, 'fit')
# The profile answers scoring needs; College Research asks for the missing ones.
RESEARCH_FIELDS = ('gpa', 'sat_score', 'ielts_score', 'target_major', 'target_countries', 'budget_usd')
EVIDENCE = ('achievements', 'honors', 'researches', 'projects', 'internships', 'activities')
SCORING_FIELDS = (
    'id', 'country', 'ranking', 'sat_min', 'sat_max', 'popular_majors', 'net_price_usd', 'acceptance_rate',
    'offers_international_aid', 'offers_merit_aid', 'offers_need_based_aid', 'test_optional',
)
# Fit sorting and band filters score at most this many plausible universities, not the whole catalogue.
FIT_CANDIDATES = 600
SAT_POINTS = 25
PRICE_POINTS = 12


def eligible_programs(*fields):
    """Programs a student from abroad can apply to: the only ones scored and listed."""
    programs = UniversityProgram.objects.filter(is_active=True, international_students_eligible=True)
    return Prefetch('programs', queryset=programs.only(*fields) if fields else programs)


# ---------------------------------------------------------------- fit scoring

def evidence_counts(profile):
    return {name: getattr(profile, name).count() for name in EVIDENCE}


def missing_fields(profile):
    return [field for field in RESEARCH_FIELDS if getattr(profile, field) in (None, '')]


def fit_context(profile):
    """What scoring reads from a profile, or None while research answers are missing."""
    if missing_fields(profile):
        return None
    counts = evidence_counts(profile)
    return {
        'gpa': float(profile.gpa),
        'gpa_scale': int(profile.effective_gpa_scale),
        'sat': int(profile.sat_score),
        'ielts': float(profile.ielts_score),
        'budget': int(profile.budget_usd),
        'countries': sorted({country_key(value) for value in profile.target_countries.split(',') if value.strip()}),
        'major': profile.target_major.strip().lower(),
        'major_name': profile.target_major,
        'scholarship_needed': bool(profile.scholarship_needed),
        'strength': min(10, sum(min(value, 2) for value in counts.values()) * 2),
    }


def score_university(university, ctx):
    """One university's fit for a ready profile. ``university.programs`` must be the eligible ones."""
    reasons = []
    gaps = []
    # Points of factors the catalogue has no data for: they are left out, not guessed.
    missing = 0
    sat = ctx['sat']
    ielts = ctx['ielts']

    academic = round(min(15, (ctx['gpa'] / ctx['gpa_scale']) * 15))
    if university.sat_min:
        if sat >= (university.sat_max or university.sat_min):
            academic += 25
            reasons.append(f'SAT {sat} meets or exceeds the catalog range')
        elif sat >= university.sat_min:
            academic += 22
            reasons.append(f'SAT {sat} fits the {university.sat_min}–{university.sat_max or university.sat_min} catalog range')
        elif sat >= max(400, university.sat_min - 80):
            academic += 12
            gaps.append(f'SAT is {university.sat_min - sat} points below the catalog minimum')
        else:
            academic += 4
            gaps.append(f'Raise SAT toward at least {university.sat_min}')
    elif university.test_optional:
        academic += 20
        reasons.append('SAT is optional at this university')
    else:
        missing += SAT_POINTS
        gaps.append('SAT range is not listed in the catalog')
    if ielts >= 7:
        academic += 8
        reasons.append(f'IELTS {ielts:g} is a strong language score')
    elif ielts >= 6.5:
        academic += 6
        reasons.append(f'IELTS {ielts:g} is suitable for many programs')
    else:
        academic += 3
        gaps.append('Verify the IELTS requirement on the official program page')

    if country_key(university.country) in ctx['countries']:
        preferences = 12
        reasons.append(f'{university.country} is one of your target countries')
    else:
        preferences = 3
    majors = [program.canonical_major.strip().lower() for program in university.programs.all()]
    majors.extend(value.strip().lower() for value in university.popular_majors.split(',') if value.strip())
    major = ctx['major']
    if major and any(major in item or item in major for item in majors):
        preferences += 10
        reasons.append(f'{ctx["major_name"]} matches an available field of study')
    else:
        preferences += 4
        gaps.append('Check the exact program requirements for your selected major')

    budget = ctx['budget']
    if university.net_price_usd:
        if university.net_price_usd <= budget:
            financial = 12
            reasons.append('Estimated net price is within your budget')
        elif university.net_price_usd <= budget * 1.5:
            financial = 7
            gaps.append('Net price is above budget but may be covered with aid')
        else:
            financial = 2
            gaps.append('Estimated net price is significantly above your budget')
    else:
        financial = 0
        missing += PRICE_POINTS
        gaps.append('Net price is not available in the catalog')
    if ctx['scholarship_needed']:
        if university.offers_international_aid or university.offers_merit_aid or university.offers_need_based_aid:
            financial += 8
            reasons.append('A suitable type of financial aid is available')
        else:
            financial += 1
            gaps.append('International or merit aid is not listed in the catalog')
    else:
        financial += 8

    earned = academic + preferences + financial + ctx['strength']
    # Score the known factors on the full scale, then take off half the missing weight:
    # a row without admissions data never outscores the same row with data that fits.
    total = min(100, round(earned * 100 / (100 - missing) * (1 - missing / 200)))
    rate = float(university.acceptance_rate) if university.acceptance_rate is not None else None
    if rate is None and not university.sat_min:
        # No admission data in the catalogue (e.g. a QS-only row): unknown, not "target".
        band = None
    elif (rate is not None and rate < 15) or (university.sat_min and sat < university.sat_min):
        band = 'reach'
    elif rate is not None and rate >= 45 and (not university.sat_min or sat >= university.sat_min):
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


def fit_candidates(ctx):
    """Universities in the student's target countries or with admissions data, best ranked first."""
    countries = University.objects.order_by().values_list('country', flat=True).distinct()
    spellings = [country for country in countries if country_key(country) in ctx['countries']]
    has_data = Q(sat_min__isnull=False) | Q(acceptance_rate__isnull=False) | Q(net_price_usd__isnull=False)
    return (
        University.objects.filter(Q(country__in=spellings) | has_data)
        .order_by(F('ranking').asc(nulls_last=True), 'name')[:FIT_CANDIDATES]
    )


def fit_scores(profile, ctx):
    """``{university_id: (score, band)}`` for the plausible universities (``fit_candidates``).

    Rows outside the candidates have no score: fit sorting puts them last and
    band filters leave them out. Cached per student, profile answers and
    catalogue version, so paging, re-sorting and refiltering never rescore.
    """
    signature = hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()[:20]
    key = f'college-fit:{profile.pk}:{cache_get(VERSION_KEY, 0)}:{signature}'
    scores = cache_get(key)
    if scores is None:
        universities = fit_candidates(ctx).only(*SCORING_FIELDS).prefetch_related(
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
    market = next((code for code, label in MARKET_COUNTRIES.items() if label == name), None)
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
    key = f'college-facets:{cache_get(VERSION_KEY, 0)}'
    facets = cache_get(key)
    if facets is None:
        facets = {
            'countries': {}, 'aid': dict.fromkeys(AID_FLAGS, 0), 'test_optional': 0, 'public': 0,
            'qs': {name: {} for name in QS_FILTERS},
        }
        rows = University.objects.values_list(
            'market', 'country', 'test_optional', 'institution_type', *AID_FLAGS,
            *(f'qs_data__{name}' for name in QS_FILTERS),
        )
        for market, country, test_optional, institution_type, *values in rows:
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
    """The catalogue counts plus the two that depend on the student: SAT in range and bands."""
    bands = dict.fromkeys(BANDS, 0)
    for _, band in scores.values():
        if band:
            bands[band] += 1
    sat_fit = University.objects.filter(sat_fit_q(profile.sat_score)).count()
    return {**catalog_facets(), 'sat_fit': sat_fit, 'bands': bands}


class CollegeSearchParams(serializers.Serializer):
    """The query string of ``GET /api/college-search/``; anything unknown is a 400."""

    search = serializers.CharField(required=False, allow_blank=True, default='', max_length=MAX_SEARCH_LENGTH)
    country = serializers.CharField(required=False, allow_blank=True, default='', max_length=120)
    price = serializers.ChoiceField(choices=('all', 'budget', *PRICE_CAPS), default='all')
    aid = serializers.CharField(required=False, allow_blank=True, default='')
    # Absent: every band. Present but empty: no band at all (every box unticked).
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
        return None if value is None else self._subset(value, BANDS, 'Choose reach, target or safety.')

    def validate_ids(self, value):
        try:
            ids = list(dict.fromkeys(int(item) for item in (value or '').split(',') if item.strip()))
        except ValueError:
            raise serializers.ValidationError('Use comma-separated university ids.')
        if len(ids) > MAX_IDS:
            raise serializers.ValidationError(f'Ask for at most {MAX_IDS} universities at a time.')
        return ids


def filtered_catalog(params, profile):
    queryset = University.objects.all()
    for term in params['search'].split():
        queryset = queryset.filter(term_query(SEARCH_FIELDS, term))
    if params['country']:
        queryset = queryset.filter(country_q(params['country']))
    if params['price'] != 'all':
        cap = int(profile.budget_usd or 0) if params['price'] == 'budget' else PRICE_CAPS[params['price']]
        queryset = queryset.filter(net_price_usd__isnull=False, net_price_usd__lte=cap)
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
    from .serializers import UniversityRowSerializer

    rows = UniversityRowSerializer(universities, many=True).data
    if ctx is not None:
        for row, university in zip(rows, universities):
            row['fit'] = score_university(university, ctx)
    return rows


def college_search(profile, params):
    """One page of College Search for ``profile`` (validated ``CollegeSearchParams``)."""
    ctx = fit_context(profile)
    rows = University.objects.prefetch_related(eligible_programs())
    if params['ids']:
        # Rows the page already knows by id (the student's list, a university page).
        return {'results': serialize_rows(list(rows.filter(pk__in=params['ids']).order_by(*ORDERINGS['ranking'])), ctx)}

    bands = params['bands']
    band_filter = bands is not None and set(bands) != set(BANDS)
    by_fit = params['sort'] == 'fit' and ctx is not None
    scores = fit_scores(profile, ctx) if ctx is not None and (by_fit or band_filter or params['facets']) else {}
    queryset = filtered_catalog(params, profile)
    if band_filter:
        queryset = queryset.filter(pk__in=[pk for pk, (_, band) in scores.items() if band in bands])

    size = params['page_size']
    start = (params['page'] - 1) * size
    if by_fit:
        ranked = sorted(queryset.values_list('pk', 'ranking'), key=lambda row: (-scores.get(row[0], (-1,))[0], row[1] or 999999))
        count = len(ranked)
        page_ids = [pk for pk, _ in ranked[start:start + size]]
        found = {university.pk: university for university in rows.filter(pk__in=page_ids)}
        page = [found[pk] for pk in page_ids if pk in found]
    else:
        # Sorting by fit needs a ready profile; until then the catalogue keeps its ranking order.
        queryset = queryset.order_by(*ORDERINGS.get(params['sort'], ORDERINGS['ranking']))
        count = queryset.count()
        page = list(queryset.prefetch_related(eligible_programs())[start:start + size])
    data = {
        'count': count,
        'page': params['page'],
        'page_size': size,
        'next': params['page'] + 1 if start + size < count else None,
        'results': serialize_rows(page, ctx),
    }
    if params['facets']:
        data['facets'] = student_facets(profile, scores)
    return data
