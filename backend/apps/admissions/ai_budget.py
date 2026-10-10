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


FEATURES = ('assistant', 'essay_coach')
TOP_SCHOOLS = 5


def _note(keys):
    """Usage and refusal counters read by the admin portal. Best effort: a cache
    failure here never blocks or refuses a call."""
    count_hits(keys, TTL_SECONDS)


def consume(feature, user):
    """Count one paid call for ``user``; ``False`` when any daily cap is reached."""
    day = timezone.localdate().isoformat()
    global_cap, school_cap, user_cap = _limits(feature)
    prefix = f'ai-budget:{feature}:{day}'
    used = [f'{prefix}:used'] + ([f'{prefix}:used:school:{user.school_id}'] if user.school_id else [])
    caps = [(prefix, global_cap), (f'{prefix}:user:{user.pk}', user_cap)]
    if user.school_id:
        caps.append((f'{prefix}:school:{user.school_id}', school_cap))
    caps = [(key, limit) for key, limit in caps if limit is not None]
    if not caps:
        _note(used)
        return True
    if any(limit <= 0 for _, limit in caps):
        _note([f'{prefix}:refused'])
        return False

    counts = count_hits([key for key, _ in caps], TTL_SECONDS)
    if counts is None:
        local_caps = [(f'{feature}:process', settings.AI_FALLBACK_PROCESS_DAILY_BUDGET)]
        if user_cap is not None:
            local_caps.append((f'{feature}:user:{user.pk}', user_cap))
        allowed = _fallback.consume(day, local_caps)
        logger.warning('ai_budget_cache_down feature=%s allowed=%s: using the per-process allowance', feature, allowed)
        return allowed
    if all(count <= limit for count, (_, limit) in zip(counts, caps)):
        _note(used)
        return True
    for key, _ in caps:
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
        school_keys = {f'{prefix}:used:school:{pk}': pk for pk in school_ids}
        values = cache_get_many([f'{prefix}:used', f'{prefix}:refused', *school_keys])
        if values is None:
            return None
        global_cap, school_cap, user_cap = _limits(feature)
        busiest = sorted(
            ((pk, int(values[key])) for key, pk in school_keys.items() if values.get(key)),
            key=lambda item: -item[1],
        )[:TOP_SCHOOLS]
        report[feature] = {
            'used': int(values.get(f'{prefix}:used') or 0),
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
