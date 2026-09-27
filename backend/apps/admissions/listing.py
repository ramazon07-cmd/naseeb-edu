"""Server-side search, filtering and ordering for list endpoints.

Each list view declares what may be searched, filtered and sorted; every
parameter is validated (a bad value is a 400, never a 500 or a silent full
scan). Pagination (page-number or keyset cursor) lives in core.pagination.

* ``?search=`` — whitespace-separated terms (up to ``MAX_SEARCH_TERMS``); every
  term must match one of ``search_fields`` (case-insensitive substring) or,
  with ``search_student_path``, the student's name/email. Same-table
  ``search_fields`` keep PostgreSQL on the trigram indexes.
* ``int_filters`` — ``{param: orm_path}``, parsed with ``int_param``.
* ``choice_filters`` — ``{param: (orm_path, choices)}``.
* ``bool_filters`` — ``{param: orm_path}``; ``true``/``false``.
* ``date_filters`` — ``{prefix: orm_path}``; ``<prefix>_from`` / ``<prefix>_to``
  accept ``YYYY-MM-DD`` or an ISO datetime and are inclusive.
* ``ordering_options`` — ``{public_name: (orm terms…)}``. Only non-null columns
  (ending in ``id``) so keyset pagination can seek on them.
"""
import datetime

from django.db.models import DateTimeField, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

from .params import int_param

MAX_SEARCH_LENGTH = 100
MAX_SEARCH_TERMS = 4
STUDENT_SEARCH_FIELDS = ('user__first_name', 'user__last_name', 'user__email', 'user__username')


def search_terms(raw):
    text = str(raw or '').strip()
    if len(text) > MAX_SEARCH_LENGTH:
        raise ValidationError({'search': [f'Use {MAX_SEARCH_LENGTH} characters or fewer.']})
    return text.split()[:MAX_SEARCH_TERMS]


def term_query(fields, term):
    query = Q()
    for field in fields:
        query |= Q(**{f'{field}__icontains': term})
    return query


def _date_bound(value, param, *, is_datetime, end):
    text = str(value).strip()
    try:
        moment = parse_datetime(text) if 'T' in text or ' ' in text else None
        day = None if moment else parse_date(text)
    except ValueError:
        moment = day = None
    if moment is None and day is None:
        raise ValidationError({param: ['Use YYYY-MM-DD or an ISO 8601 date-time.']})
    if not is_datetime:
        return (moment.date() if moment else day), ('lte' if end else 'gte')
    if moment is None:
        start = timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))
        # An inclusive end date covers the whole day.
        return (start + datetime.timedelta(days=1), 'lt') if end else (start, 'gte')
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment, ('lte' if end else 'gte')


class ListQueryMixin:
    search_fields = ()
    search_student_path = None
    int_filters = {}
    choice_filters = {}
    bool_filters = {}
    date_filters = {}
    ordering_options = {}
    # Used in page-number mode only when set; None keeps the queryset order.
    default_ordering = None
    # Keyset (cursor) mode needs a whitelisted ordering.
    default_cursor_ordering = None

    keyset_ordering = None

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if getattr(self, 'action', None) != 'list':
            return queryset
        return self.apply_list_query(queryset, self.request.query_params)

    def apply_list_query(self, queryset, params):
        queryset = self.apply_search(queryset, params.get('search'))
        queryset = self.apply_filters(queryset, params)
        return self.apply_ordering(queryset, params)

    def apply_search(self, queryset, raw):
        terms = search_terms(raw)
        if not terms or not (self.search_fields or self.search_student_path):
            return queryset
        from .models import StudentProfile

        for term in terms:
            condition = term_query(self.search_fields, term)
            if self.search_student_path:
                # A subquery on the (indexed) user columns, so the outer table
                # can combine it with its own indexes instead of joining.
                matching = StudentProfile.objects.filter(term_query(STUDENT_SEARCH_FIELDS, term)).values('pk')
                condition |= Q(**{f'{self.search_student_path}__in': matching})
            queryset = queryset.filter(condition)
        return queryset

    def apply_filters(self, queryset, params):
        lookups = {}
        for param, path in self.int_filters.items():
            value = int_param(params, param)
            if value is not None:
                lookups[path] = value
        for param, (path, choices) in self.choice_filters.items():
            value = params.get(param)
            if value in (None, ''):
                continue
            allowed = {str(choice[0]) if isinstance(choice, (list, tuple)) else str(choice) for choice in choices}
            if value not in allowed:
                raise ValidationError({param: [f'Choose one of: {", ".join(sorted(allowed))}.']})
            lookups[path] = value
        for param, path in self.bool_filters.items():
            value = params.get(param)
            if value in (None, ''):
                continue
            if value not in {'true', 'false', '1', '0'}:
                raise ValidationError({param: ['Use true or false.']})
            lookups[path] = value in {'true', '1'}
        model = queryset.model
        for prefix, path in self.date_filters.items():
            field = model._meta.get_field(path) if '__' not in path else None
            is_datetime = isinstance(field, DateTimeField)
            for suffix, end in (('from', False), ('to', True)):
                param = f'{prefix}_{suffix}'
                value = params.get(param)
                if value in (None, ''):
                    continue
                bound, operator = _date_bound(value, param, is_datetime=is_datetime, end=end)
                lookups[f'{path}__{operator}'] = bound
        return queryset.filter(**lookups) if lookups else queryset

    def apply_ordering(self, queryset, params):
        cursor_mode = 'cursor' in params
        name = params.get('ordering') or (self.default_cursor_ordering if cursor_mode else self.default_ordering)
        if not name:
            return queryset
        if name not in self.ordering_options:
            raise ValidationError({'ordering': [f'Choose one of: {", ".join(sorted(self.ordering_options))}.']})
        terms = self.ordering_options[name]
        self.keyset_ordering = terms
        return queryset.order_by(*terms)
