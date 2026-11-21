"""Daily caps on paid AI provider calls: across the platform, per school and per user.

All caps for one call are counted in a single atomic cache step; if any is
exceeded the whole call is refunded and refused, so a rejected call never
eats into another cap.

Throttles fail open when the cache is down, but a budget must not: a Redis
outage would otherwise mean unlimited paid calls. While the cache is
unreachable each process falls back to its own small in-memory daily
allowance (AI_FALLBACK_PROCESS_DAILY_BUDGET, 0 = no AI during an outage),
so the worst-case spend is bounded by the number of processes.
"""
import logging
import threading

from django.conf import settings
from django.utils import timezone

from apps.users.cache_safety import cache_decrement, cache_get_many, count_hits

logger = logging.getLogger('naseeb.ai_budget')
TTL_SECONDS = 26 * 60 * 60


def _limits(feature):
    """(global, per school, per user) daily caps; ``None`` means no cap."""
    if feature == 'assistant':
        # Kept from the original settings: 0 = no global/per-user cap.
        return (
            settings.AI_ASSISTANT_DAILY_BUDGET or None,
            settings.AI_ASSISTANT_SCHOOL_DAILY_BUDGET or None,
            settings.AI_ASSISTANT_USER_DAILY_LIMIT or None,
        )
    if feature == 'essay_coach':
        # ESSAY_COACH_DAILY_BUDGET=0 has always meant "no AI checks at all".
        return (
            settings.ESSAY_COACH_DAILY_BUDGET,
            settings.ESSAY_COACH_SCHOOL_DAILY_BUDGET or None,
            settings.ESSAY_COACH_USER_DAILY_LIMIT or None,
        )
    if feature == 'recommendation_letter':
        # Like the coach: a platform budget of 0 turns AI suggestions off.
        return (
            settings.REC_LETTER_AI_DAILY_BUDGET,
            settings.REC_LETTER_AI_SCHOOL_DAILY_BUDGET or None,
            settings.REC_LETTER_AI_USER_DAILY_LIMIT or None,
        )
    if feature == 'telegram_import':
        # A nightly job with no user or school: one platform cap (0 = import off).
        return (settings.TELEGRAM_IMPORT_DAILY_BUDGET, None, None)
    raise ValueError(f'Unknown AI feature: {feature}')


class _ProcessFallback:
    """Per-process daily counters used only while the shared cache is down."""

    def __init__(self):
        self.lock = threading.Lock()
        self.day = None
        self.counts = {}

    def consume(self, day, caps):
        with self.lock:
            if day != self.day:
                self.day, self.counts = day, {}
            if any(self.counts.get(key, 0) >= limit for key, limit in caps):
                return False
            for key, _ in caps:
                self.counts[key] = self.counts.get(key, 0) + 1
            return True


_fallback = _ProcessFallback()


FEATURES = ('assistant', 'essay_coach', 'recommendation_letter')
TOP_SCHOOLS = 5


def _note(keys):
    """Refusal counters read by the admin portal. Best effort: a cache failure
    here never blocks or refuses a call."""
    count_hits(keys, TTL_SECONDS)


def consume(feature, user):
    """Count one paid call for ``user``; ``False`` when any daily cap is reached.

    The platform and school counters are counted on every call, capped or not:
    they are also today's usage on the admin portal, so one atomic step both
    checks the caps and records the call.
    """
    day = timezone.localdate().isoformat()
    global_cap, school_cap, user_cap = _limits(feature)
    prefix = f'ai-budget:{feature}:{day}'
    counters = [(prefix, global_cap)]
    if user.school_id:
        counters.append((f'{prefix}:school:{user.school_id}', school_cap))
    if user_cap is not None:
        counters.append((f'{prefix}:user:{user.pk}', user_cap))
    capped = [limit for _, limit in counters if limit is not None]
    if any(limit <= 0 for limit in capped):
        _note([f'{prefix}:refused'])
        return False

    counts = count_hits([key for key, _ in counters], TTL_SECONDS)
    if counts is None:
        if not capped:
            return True
        local_caps = [(f'{feature}:process', settings.AI_FALLBACK_PROCESS_DAILY_BUDGET)]
        if user_cap is not None:
            local_caps.append((f'{feature}:user:{user.pk}', user_cap))
        allowed = _fallback.consume(day, local_caps)
        logger.warning('ai_budget_cache_down feature=%s allowed=%s: using the per-process allowance', feature, allowed)
        return allowed
    if all(limit is None or count <= limit for count, (_, limit) in zip(counts, counters)):
        return True
    for key, _ in counters:
        cache_decrement(key)
    _note([f'{prefix}:refused'])
    return False


def usage_today(school_ids):
    """Today's calls, caps and refusals per feature, plus the busiest schools.

    Read-only: nothing is incremented. ``None`` when the cache cannot be read.
    """
    day = timezone.localdate().isoformat()
    report = {}
    for feature in FEATURES:
        prefix = f'ai-budget:{feature}:{day}'
        school_keys = {f'{prefix}:school:{pk}': pk for pk in school_ids}
        values = cache_get_many([prefix, f'{prefix}:refused', *school_keys])
        if values is None:
            return None
        global_cap, school_cap, user_cap = _limits(feature)
        busiest = sorted(
            ((pk, int(values[key])) for key, pk in school_keys.items() if values.get(key)),
            key=lambda item: -item[1],
        )[:TOP_SCHOOLS]
        report[feature] = {
            'used': int(values.get(prefix) or 0),
            'limit': global_cap,
            'school_limit': school_cap,
            'user_limit': user_cap,
            'refused': int(values.get(f'{prefix}:refused') or 0),
            'top_schools': [{'id': pk, 'used': count} for pk, count in busiest],
        }
    return report


def fallback_active():
    """Whether this process fell back to its own allowance today (cache unreachable)."""
    return _fallback.day == timezone.localdate().isoformat() and bool(_fallback.counts)


def consume_job(feature):
    """Count one paid call made by a scheduled job (no user); ``False`` when the daily cap is reached.

    Like :func:`consume`, a refused call is undone at once. While the cache is down the
    job may use at most AI_FALLBACK_PROCESS_DAILY_BUDGET calls (and never more than its cap).
    """
    day = timezone.localdate().isoformat()
    cap = _limits(feature)[0]
    prefix = f'ai-budget:{feature}:{day}'
    if cap is None or cap <= 0:
        _note([f'{prefix}:refused'])
        return False
    counts = count_hits([prefix], TTL_SECONDS)
    if counts is None:
        local_cap = min(cap, settings.AI_FALLBACK_PROCESS_DAILY_BUDGET)
        allowed = _fallback.consume(day, [(f'{feature}:process', local_cap)])
        logger.warning('ai_budget_cache_down feature=%s allowed=%s: using the per-process allowance', feature, allowed)
        return allowed
    if counts[0] <= cap:
        return True
    cache_decrement(prefix)
    _note([f'{prefix}:refused'])
    return False


def refund_job(feature):
    """Give back one call counted by :func:`consume_job` whose provider call failed."""
    day = timezone.localdate().isoformat()
    prefix = f'ai-budget:{feature}:{day}'
    if cache_get_many([prefix]) is None:
        with _fallback.lock:
            key = f'{feature}:process'
            if _fallback.day == day and _fallback.counts.get(key):
                _fallback.counts[key] -= 1
        return
    cache_decrement(prefix)
