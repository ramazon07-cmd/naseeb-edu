"""What a student from abroad pays per year: the one rule for price filters, sorting, fit and display.

* ``cost``: a US university's ``intl_cost_usd`` (cost of attendance for an international
  student); everywhere else its ``net_price_usd``. The price filter, the price sort and
  the fit's budget factor compare this and nothing else.
* ``cost_label``: ``international_cost`` or ``net_price``, which the frontend translates.
* ``after_aid_usd``: Scorecard's net price for a US university that gives international
  students aid. It is the average for US students after aid, so it is only shown as a
  secondary line and never compared with a budget.
"""
from django.db.models import Case, CharField, F, IntegerField, Value, When

from .models import University

US = University.Market.US
COST_ANNOTATIONS = {
    'cost': Case(When(market=US, then=F('intl_cost_usd')), default=F('net_price_usd'), output_field=IntegerField()),
    'cost_label': Case(When(market=US, then=Value('international_cost')), default=Value('net_price'), output_field=CharField()),
    'after_aid_usd': Case(
        When(market=US, offers_international_aid=True, then=F('net_price_usd')), default=None, output_field=IntegerField(),
    ),
}
COST_FIELDS = tuple(COST_ANNOTATIONS)


def with_cost(queryset):
    return queryset.annotate(**COST_ANNOTATIONS)


def cost_fields(university):
    """``{cost, cost_label, after_aid_usd}``: the annotation, or one query for a row loaded without it."""
    if not hasattr(university, 'cost'):
        row = with_cost(University.objects.filter(pk=university.pk)).values(*COST_FIELDS).first() or dict.fromkeys(COST_FIELDS)
        for name, value in row.items():
            setattr(university, name, value)
    return {name: getattr(university, name) for name in COST_FIELDS}


def forget_cost(university):
    """Drop a stale annotation after the row's prices changed."""
    for name in COST_FIELDS:
        university.__dict__.pop(name, None)
