"""List pagination shared by every collection endpoint.

Two modes behind one class, so every list speaks the same contract:

* page-number (default, unchanged response shape):
  ``{"count", "next", "previous", "results"}`` with ``?page=`` and
  ``?page_size=`` (capped at 100). ``count`` is exact up to
  ``EXACT_COUNT_LIMIT`` rows; above that the exact figure is cached for
  ``COUNT_CACHE_SECONDS`` per distinct query (the scoping filters are part of
  the SQL, so each school/counselor gets its own entry).
* keyset cursor (``?cursor=`` present, empty for the first page):
  ``{"results", "next", "has_more"}``. The cursor holds the ordering values of
  the last row, so page N costs the same as page 1 (no OFFSET scan) and rows
  inserted while a client pages through are neither duplicated nor skipped.
  No COUNT is run in this mode.
"""
import base64
import binascii
import datetime
import decimal
import hashlib
import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator as DjangoPaginator
from django.db.models import F, Q
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param

from apps.users.cache_safety import cache_get, cache_set

MAX_PAGE_SIZE = 100
EXACT_COUNT_LIMIT = 1000
COUNT_CACHE_SECONDS = 60
DEFAULT_KEYSET_ORDERING = ('-id',)
MAX_ID = 2 ** 63 - 1


class BoundedCountPaginator(DjangoPaginator):
    """Counts at most ``EXACT_COUNT_LIMIT + 1`` rows per request.

    Small collections (every student- or counselor-scoped list) get an exact
    count from a LIMITed subquery. Beyond the limit a full COUNT(*) runs at
    most once per minute per query shape.
    """

    @cached_property
    def count(self):
        queryset = self.object_list
        if not hasattr(queryset, 'query'):
            return super().count
        bounded = queryset[:EXACT_COUNT_LIMIT + 1].count()
        if bounded <= EXACT_COUNT_LIMIT:
            return bounded
        sql, params = queryset.query.sql_with_params()
        digest = hashlib.sha256(repr((queryset.db, sql, params)).encode()).hexdigest()
        key = f'list-count:{digest}'
        cached = cache_get(key)
        if cached is not None:
            return cached
        total = queryset.count()
        cache_set(key, total, COUNT_CACHE_SECONDS)
        return total


def _encode_value(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


def _valid_cursor_value(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -MAX_ID <= value <= MAX_ID
    return isinstance(value, str) and len(value) <= 500


def _row_value(obj, path):
    value = obj
    for part in path.split('__'):
        value = getattr(value, part)
    return value


def keyset_filter(ordering, values):
    """Rows strictly after ``values`` in ``ordering`` (row-value comparison).

    ``(a, b, c) > (x, y, z)`` expands to ``a > x OR (a = x AND b > y) OR
    (a = x AND b = y AND c > z)``, with ``<`` for descending fields.
    """
    condition = Q()
    equal = Q()
    for term, value in zip(ordering, values):
        descending = term.startswith('-')
        field = term.lstrip('-')
        step = Q(**{f'{field}__{"lt" if descending else "gt"}': value})
        condition |= equal & step
        equal &= Q(**{field: value})
    return condition


class ListPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE
    django_paginator_class = BoundedCountPaginator
    cursor_query_param = 'cursor'

    keyset_mode = False

    def paginate_queryset(self, queryset, request, view=None):
        if self.cursor_query_param not in request.query_params:
            return super().paginate_queryset(queryset, request, view)
        return self.paginate_keyset(queryset, request, view)

    def get_paginated_response(self, data):
        if not self.keyset_mode:
            return super().get_paginated_response(data)
        return Response({'results': data, 'next': self.next_link, 'has_more': self.next_link is not None})

    def get_paginated_response_schema(self, schema):
        response = super().get_paginated_response_schema(schema)
        response['properties']['has_more'] = {'type': 'boolean', 'example': False}
        return response

    # Keyset mode -----------------------------------------------------------

    def keyset_ordering(self, queryset, view):
        # Views using ListQueryMixin expose a whitelisted ordering of
        # non-null columns; anything else pages newest-first by id.
        ordering = tuple(getattr(view, 'keyset_ordering', None) or ()) or DEFAULT_KEYSET_ORDERING
        if ordering[-1].lstrip('-') not in {'id', 'pk'}:
            ordering = (*ordering, '-id' if ordering[-1].startswith('-') else 'id')
        return ordering

    def decode_cursor(self, raw, signature):
        if not raw:
            return None
        try:
            padded = raw + '=' * (-len(raw) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise ValidationError({self.cursor_query_param: ['Invalid cursor.']})
        if (
            not isinstance(payload, dict)
            or payload.get('o') != signature
            or not isinstance(payload.get('v'), list)
            or len(payload['v']) != signature.count(',') + 1
            or not all(_valid_cursor_value(value) for value in payload['v'])
        ):
            raise ValidationError({self.cursor_query_param: ['Invalid cursor.']})
        return payload['v']

    @staticmethod
    def encode_cursor(values, signature):
        payload = json.dumps({'o': signature, 'v': [_encode_value(value) for value in values]}, separators=(',', ':'))
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')

    def paginate_keyset(self, queryset, request, view):
        self.keyset_mode = True
        self.request = request
        page_size = self.get_page_size(request)
        ordering = self.keyset_ordering(queryset, view)
        signature = ','.join(ordering)
        values = self.decode_cursor(request.query_params.get(self.cursor_query_param, '').strip(), signature)
        queryset = queryset.order_by(*[
            F(term[1:]).desc() if term.startswith('-') else F(term).asc() for term in ordering
        ])
        if values is not None:
            try:
                queryset = queryset.filter(keyset_filter(ordering, values))
                rows = list(queryset[:page_size + 1])
            except (ValueError, TypeError, decimal.InvalidOperation, DjangoValidationError):
                raise ValidationError({self.cursor_query_param: ['Invalid cursor.']})
        else:
            rows = list(queryset[:page_size + 1])
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        self.next_link = None
        if has_more:
            last = rows[-1]
            cursor = self.encode_cursor([_row_value(last, term.lstrip('-')) for term in ordering], signature)
            url = replace_query_param(request.build_absolute_uri(), self.cursor_query_param, cursor)
            self.next_link = remove_query_param(url, self.page_query_param)
        return rows
