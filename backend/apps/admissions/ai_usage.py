"""Per-call AI token accounting for the financial model.

Only counts are stored (tokens, latency, model, status): never a prompt, an
essay, a student fact or a reply. Recording never raises, so a logging problem
cannot fail an AI feature.

A request function calls ``capture`` with the provider's response; the caller
then calls ``record`` once. Synchronous calls share a per-thread sink; the
streaming assistant passes its own sink because its reply is read later.
"""
import logging
import re
import threading
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings

from django.utils import timezone, translation

from .models import AiUsageLog

logger = logging.getLogger('naseeb.ai_usage')

OK = AiUsageLog.Status.OK
LOCAL_FALLBACK = AiUsageLog.Status.LOCAL_FALLBACK
PROVIDER_ERROR = AiUsageLog.Status.PROVIDER_ERROR
BUDGET_REFUSED = AiUsageLog.Status.BUDGET_REFUSED
FAILED = 'failed'
PERCENTILES = (50, 90)
FEATURES = ('assistant', 'essay_coach', 'recommendation_letter', 'education_match')
_SNAPSHOT_SUFFIX = re.compile(r'-(?:\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$')
_local = threading.local()


def begin():
    """Start a fresh sink for one provider call and make it this thread's current one."""
    sink = {'started': time.monotonic()}
    _local.sink = sink
    return sink


def current_sink():
    return getattr(_local, 'sink', None)


def _chars(messages):
    total = 0
    for message in messages or []:
        content = message.get('content') if isinstance(message, dict) else ''
        total += len(content) if isinstance(content, str) else 0
    return total


def _usage_of(payload):
    usage = payload.get('usage') if isinstance(payload, dict) else None
    return usage if isinstance(usage, dict) else None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def capture(payload, body=None, sink=None):
    """Remember the usage and model of a provider response (a whole reply or one stream event)."""
    try:
        sink = sink if sink is not None else getattr(_local, 'sink', None)
        if sink is None or not isinstance(payload, dict):
            return
        if body is not None:
            sink['requested_model'] = body.get('model', '')
            sink['input_chars'] = _chars(body.get('messages'))
        if payload.get('model'):
            sink['model'] = str(payload['model'])
        usage = _usage_of(payload)
        if usage:
            sink['usage'] = usage
        choices = payload.get('choices')
        if usage or (isinstance(choices, list) and choices):
            sink['answered'] = True
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if isinstance(content, str):
                sink['output_chars'] = len(content)
    except Exception:
        logger.exception('Could not capture AI usage')


def failure_status(sink):
    return AiUsageLog.Status.INVALID_OUTPUT if sink and sink.get('answered') else AiUsageLog.Status.PROVIDER_ERROR


def _tokens(sink, output_chars):
    usage = (sink or {}).get('usage')
    if usage:
        details_in = usage.get('prompt_tokens_details') or {}
        details_out = usage.get('completion_tokens_details') or {}
        input_tokens = _count(usage.get('prompt_tokens'))
        output_tokens = _count(usage.get('completion_tokens'))
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cached_input_tokens': _count(details_in.get('cached_tokens')) if isinstance(details_in, dict) else 0,
            'reasoning_tokens': _count(details_out.get('reasoning_tokens')) if isinstance(details_out, dict) else 0,
            'total_tokens': _count(usage.get('total_tokens')) or input_tokens + output_tokens,
            'usage_estimated': False,
        }
    input_tokens = (sink or {}).get('input_chars', 0) // 4
    output_tokens = (output_chars or (sink or {}).get('output_chars', 0)) // 4
    return {
        'input_tokens': input_tokens, 'output_tokens': output_tokens, 'cached_input_tokens': 0,
        'reasoning_tokens': 0, 'total_tokens': input_tokens + output_tokens, 'usage_estimated': True,
    }


def _same_model(used, requested):
    def base(name):
        return _SNAPSHOT_SUFFIX.sub('', name.split('/')[-1])
    return base(used) == base(requested)


def record(feature, user, *, provider, status, sink=None, output_chars=0):
    """Store one call. ``status`` may be ``FAILED`` to derive provider_error / invalid_output.

    Refusals and local answers carry no tokens. ``fallback_used`` is true when the
    provider reports a different model than the one requested (the gateway's own fallback).
    """
    try:
        sink = sink if sink is not None else getattr(_local, 'sink', None)
        _local.sink = None
        if status == FAILED:
            status = failure_status(sink)
        paid = status in (AiUsageLog.Status.OK, AiUsageLog.Status.PROVIDER_ERROR, AiUsageLog.Status.INVALID_OUTPUT)
        started = (sink or {}).get('started')
        model = (sink or {}).get('model') or (sink or {}).get('requested_model', '')
        requested = (sink or {}).get('requested_model', '')
        fields = _tokens(sink, output_chars) if paid and (sink or {}).get('answered') else {
            'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0,
            'reasoning_tokens': 0, 'total_tokens': 0, 'usage_estimated': False,
        }
        AiUsageLog.objects.create(
            user=user if getattr(user, 'pk', None) else None,
            school_id=getattr(user, 'school_id', None),
            role=str(getattr(user, 'role', '') or '')[:30],
            feature=feature,
            provider=provider if paid else '',
            model=model[:120] if paid else '',
            status=status,
            latency_ms=round((time.monotonic() - started) * 1000) if paid and started else 0,
            language=(translation.get_language() or '')[:10],
            fallback_used=bool(paid and model and requested and not _same_model(model, requested)),
            **fields,
        )
    except Exception:
        logger.exception('Could not record AI usage for %s', feature)


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    index = max(0, min(len(sorted_values) - 1, -(-len(sorted_values) * pct // 100) - 1))
    return sorted_values[index]


def prices():
    """(input, output) USD per 1M tokens from settings, or ``None`` when not both set."""
    try:
        low, high = (Decimal(str(getattr(settings, name, '') or '')) for name in ('AI_PRICE_INPUT_USD_PER_1M', 'AI_PRICE_OUTPUT_USD_PER_1M'))
    except InvalidOperation:
        return None
    return (low, high) if low >= 0 and high >= 0 and (low or high) else None


def cost_usd(input_tokens, output_tokens, price=None):
    price = price or prices()
    if price is None:
        return None
    return float(round((Decimal(input_tokens) * price[0] + Decimal(output_tokens) * price[1]) / Decimal(1_000_000), 6))


def _summarize(rows):
    """Rows are (input, output, cached, reasoning, total, status, fallback_used, estimated, latency_ms)."""
    calls = len(rows)
    paid = [row for row in rows if row[5] in ('ok', 'provider_error', 'invalid_output')]
    ok = [row for row in rows if row[5] == 'ok']
    result = {
        'calls': calls,
        'paid_calls': len(paid),
        'ok_calls': len(ok),
        'error_rate': round(sum(1 for row in paid if row[5] != 'ok') / len(paid), 4) if paid else 0,
        'fallback_rate': round(sum(1 for row in paid if row[6]) / len(paid), 4) if paid else 0,
        'budget_refused': sum(1 for row in rows if row[5] == 'budget_refused'),
        'local_fallback': sum(1 for row in rows if row[5] == 'local_fallback'),
        'estimated_calls': sum(1 for row in paid if row[7]),
    }
    latencies = sorted(row[8] for row in paid if row[8] > 0)
    result['latency_ms'] = {
        'avg': round(sum(latencies) / len(latencies)) if latencies else 0,
        'p50': _percentile(latencies, 50), 'p95': _percentile(latencies, 95),
        'max': latencies[-1] if latencies else 0,
    }
    for name, index in (('input', 0), ('output', 1), ('cached_input', 2), ('reasoning', 3), ('total', 4)):
        values = sorted(row[index] for row in paid)
        result[f'{name}_tokens'] = {
            'sum': sum(values),
            'avg': round(sum(values) / len(values), 1) if values else 0,
            'max': values[-1] if values else 0,
            **{f'p{pct}': _percentile(values, pct) for pct in PERCENTILES},
        }
    result['cost_usd'] = cost_usd(result['input_tokens']['sum'], result['output_tokens']['sum'])
    return result


def summary(since, feature=None):
    """Per-feature, per-school and per-day aggregates since ``since``. Counters only."""
    queryset = AiUsageLog.objects.filter(created_at__gte=since)
    if feature:
        queryset = queryset.filter(feature=feature)
    by_feature, by_school, by_day = defaultdict(list), defaultdict(list), defaultdict(list)
    rows = queryset.values_list(
        'feature', 'school_id', 'created_at', 'input_tokens', 'output_tokens', 'cached_input_tokens',
        'reasoning_tokens', 'total_tokens', 'status', 'fallback_used', 'usage_estimated', 'latency_ms',
    ).iterator(chunk_size=2000)
    for name, school_id, created_at, *rest in rows:
        rest = tuple(rest)
        by_feature[name].append(rest)
        by_school[(name, school_id)].append(rest)
        by_day[(name, timezone.localtime(created_at).date().isoformat())].append(rest)
    return {
        'since': since,
        'features': {name: _summarize(rows) for name, rows in sorted(by_feature.items())},
        'schools': [
            {'feature': name, 'school_id': school_id, **_summarize(rows)}
            for (name, school_id), rows in sorted(by_school.items(), key=lambda item: (item[0][0], item[0][1] or 0))
        ],
        'days': [
            {'feature': name, 'day': day, **_summarize(rows)}
            for (name, day), rows in sorted(by_day.items())
        ],
    }


MONITOR_FIELDS = ('calls', 'paid_calls', 'ok_calls', 'error_rate', 'fallback_rate', 'budget_refused', 'local_fallback')


def monitoring(since):
    """Compact per-feature health figures for the admin Health page: counts, error rate,
    latency p50/p95, tokens and estimated cost. Every feature is listed, even with no calls."""
    data = summary(since)
    features = {}
    for name in FEATURES:
        row = data['features'].get(name) or _summarize([])
        features[name] = {
            **{field: row[field] for field in MONITOR_FIELDS},
            'latency_p50_ms': row['latency_ms']['p50'],
            'latency_p95_ms': row['latency_ms']['p95'],
            'input_tokens': row['input_tokens']['sum'],
            'output_tokens': row['output_tokens']['sum'],
            'cost_usd': row['cost_usd'],
        }
    return features


def purge(older_than):
    """Delete rows created before ``older_than``; returns how many."""
    return AiUsageLog.objects.filter(created_at__lt=older_than).delete()[0]
