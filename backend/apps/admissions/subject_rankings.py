"""The QS subject ranking as a table: one page of one subject, best rank first.

``GET /api/subject-rankings/?subject=COM02&limit=25&offset=0`` answers with only what the Subject rankings
view shows for those rows (rank as published, university, subject score and the indicator scores the subject
uses), so a page is a few kilobytes. It is read only when a student opens that view and is never part of
College Search or the catalogue lists.

The rows are ordered in the database on the (subject_code, rank) index, the newest year loaded is picked by
one subquery, and a page costs two queries (count and rows) however many rows it holds. Pages are cached
under the catalogue cache version (``catalog_cache``), so loading new rankings or editing a university
replaces them at once; every student asks for the same pages, so one cached answer serves them all.
"""
import hashlib
import json

from django.db.models import F, Subquery
from rest_framework import serializers

from apps.users.cache_safety import cache_get, cache_set

from .catalog_cache import CACHE_SECONDS, VERSION_KEY
from .college_search import QS_FILTERS, SEARCH_FIELDS, country_q
from .listing import MAX_SEARCH_LENGTH, search_terms, term_query
from .models import University, UniversitySubjectRank
from .subjects import SUBJECTS, subject_indicators

PAGE_LIMITS = (10, 25, 50)
SOURCE = 'QS World University Rankings by Subject'
MAX_OFFSET = 5000
# The columns of a row, besides the indicator scores.
ROW_FIELDS = (
    'university_id', 'university__name', 'university__city', 'university__country', 'rank', 'rank_label', 'score', 'year',
)
# Everything that changes which rows match (not the page): part of the cache key.
FILTERS = ('subject', 'search', 'country', *QS_FILTERS)


class SubjectRankingParams(serializers.Serializer):
    """The query string of ``GET /api/subject-rankings/``; anything unknown is a 400."""

    subject = serializers.ChoiceField(choices=tuple(SUBJECTS))
    limit = serializers.ChoiceField(
        choices=PAGE_LIMITS, default=PAGE_LIMITS[0], error_messages={'invalid_choice': 'Choose 10, 25 or 50.'},
    )
    offset = serializers.IntegerField(min_value=0, max_value=MAX_OFFSET, default=0)
    search = serializers.CharField(required=False, allow_blank=True, default='', max_length=MAX_SEARCH_LENGTH)
    country = serializers.CharField(required=False, allow_blank=True, default='', max_length=120)
    region = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    size = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    focus = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)
    research = serializers.CharField(required=False, allow_blank=True, default='', max_length=40)

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({name: 'Unknown parameter.' for name in unknown})
        return attrs

    def validate_search(self, value):
        return ' '.join(search_terms(value))


def university_filter(params):
    """The universities matching the search, country and QS filters, or None when none is set."""
    if not (params['search'] or params['country'] or any(params[name] for name in QS_FILTERS)):
        return None
    universities = University.objects.all()
    for term in params['search'].split():
        universities = universities.filter(term_query(SEARCH_FIELDS, term, 'search_text'))
    if params['country']:
        universities = universities.filter(country_q(params['country']))
    for name in QS_FILTERS:
        if params[name]:
            universities = universities.filter(**{f'qs_data__{name}': params[name]})
    return universities.values('pk')


def number(value):
    return None if value is None else float(value)


def subject_ranking(params):
    """One page of the subject's ranking as a plain dict (see the module docstring); not cached."""
    code = params['subject']
    indicators = subject_indicators(code)
    fields = [f'{name}_score' for name, _ in indicators]
    # The newest year loaded for this subject, in the same query as the rows. Filtered by the code already known,
    # not by the outer row's, so the database works it out once instead of once per candidate row.
    newest = UniversitySubjectRank.objects.filter(subject_code=code).order_by('-year').values('year')[:1]
    queryset = UniversitySubjectRank.objects.filter(subject_code=code, year=Subquery(newest))
    universities = university_filter(params)
    if universities is not None:
        queryset = queryset.filter(university__in=universities)
    # A published range ('201-250') is stored as its lower bound, so its members tie on rank and the better
    # score goes first, then the name.
    queryset = queryset.order_by('rank', F('score').desc(nulls_last=True), 'university__name', 'id')
    start = params['offset']
    page = list(queryset.values(*ROW_FIELDS, *fields)[start:start + params['limit']])
    count = queryset.count()
    rows = [{
        'id': row['university_id'], 'name': row['university__name'], 'city': row['university__city'],
        'country': row['university__country'], 'rank': row['rank'], 'label': row['rank_label'], 'score': row['score'],
        'values': [number(row[field]) for field in fields],
    } for row in page]
    end = start + len(rows)
    return {
        'subject': code,
        'source': SOURCE,
        'year': page[0]['year'] if page else None,
        'indicators': [{'key': name, 'weight': weight} for name, weight in indicators],
        'count': count,
        'offset': start,
        'limit': params['limit'],
        'next_offset': end if end < count else None,
        'results': rows,
    }


def cached_subject_ranking(params):
    """``subject_ranking`` served from the catalogue cache: every student asks for the same few pages."""
    key_params = json.dumps({name: params[name] for name in (*FILTERS, 'limit', 'offset')}, sort_keys=True)
    key = f'subject-rankings:{cache_get(VERSION_KEY, 0)}:{hashlib.sha256(key_params.encode()).hexdigest()[:24]}'
    data = cache_get(key)
    if data is None:
        data = subject_ranking(params)
        cache_set(key, data, CACHE_SECONDS)
    return data
