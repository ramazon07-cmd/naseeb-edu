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

from apps.users.cache_safety import cache_decrement, count_hits

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


def consume(feature, user):
    """Count one paid call for ``user``; ``False`` when any daily cap is reached."""
    day = timezone.localdate().isoformat()
    global_cap, school_cap, user_cap = _limits(feature)
    prefix = f'ai-budget:{feature}:{day}'
    caps = [(prefix, global_cap), (f'{prefix}:user:{user.pk}', user_cap)]
    if user.school_id:
        caps.append((f'{prefix}:school:{user.school_id}', school_cap))
    caps = [(key, limit) for key, limit in caps if limit is not None]
    if not caps:
        return True
    if any(limit <= 0 for _, limit in caps):
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
        return True
    for key, _ in caps:
        cache_decrement(key)
    return False
