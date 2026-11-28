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

from apps.users.cache_safety import cache_add_amount, cache_decrement, cache_get_many, count_hits

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
    if feature == 'recommendation_letter_check':
        # Like the coach: a platform budget of 0 turns AI letter checks off.
        return (
            settings.REC_LETTER_CHECK_DAILY_BUDGET,
            settings.REC_LETTER_CHECK_SCHOOL_DAILY_BUDGET or None,
            settings.REC_LETTER_CHECK_USER_DAILY_LIMIT or None,
        )
    if feature == 'college_match_reasons':
        # Like the coach: a platform budget of 0 turns the "Why these fit you" lines off.
        return (
            settings.COLLEGE_MATCH_REASONS_DAILY_BUDGET,
            settings.COLLEGE_MATCH_REASONS_SCHOOL_DAILY_BUDGET or None,
            settings.COLLEGE_MATCH_REASONS_USER_DAILY_LIMIT or None,
        )
    if feature == 'telegram_import':
        # A nightly job with no user or school: one platform cap (0 = import off).
        return (settings.TELEGRAM_IMPORT_DAILY_BUDGET, None, None)
    if feature == 'education_match':
        # Like the coach: a platform budget of 0 turns the AI explanation off.
        return (
            settings.EDUCATION_MATCH_DAILY_BUDGET,
            settings.EDUCATION_MATCH_SCHOOL_DAILY_BUDGET or None,
            settings.EDUCATION_MATCH_USER_DAILY_LIMIT or None,
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

    def refund(self, day, keys):
        with self.lock:
            if day == self.day:
                for key in keys:
                    if self.counts.get(key, 0) > 1:
                        self.counts[key] -= 1
                    else:
                        # Drop a key that reaches zero so "fell back today" means a call really stayed counted here.
                        self.counts.pop(key, None)


_fallback = _ProcessFallback()


class Reservation:
    """One counted call: which backend took it and the exact keys/day it counted.

    Truthy, so ``if consume(...)`` keeps working; ``refund`` undoes only this.
    """

    def __init__(self, backend, day, keys=()):
        self.backend = backend  # 'cache', 'process' or None (nothing was counted)
        self.day = day
        self.keys = tuple(keys)

    def __bool__(self):
        return True


FEATURES = ('assistant', 'essay_coach', 'recommendation_letter', 'recommendation_letter_check', 'college_match_reasons', 'education_match', 'telegram_import')
TOP_SCHOOLS = 5


def _note(keys):
    """Refusal counters read by the admin portal. Best effort: a cache failure
    here never blocks or refuses a call."""
    count_hits(keys, TTL_SECONDS)


def consume(feature, user):
    """Count one paid call for ``user``; ``False`` when any daily cap is reached.

    Otherwise returns a truthy :class:`Reservation` to hand to :func:`refund`.

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
            return Reservation(None, day)
        local_caps = [(f'{feature}:process', settings.AI_FALLBACK_PROCESS_DAILY_BUDGET)]
        if user_cap is not None:
            local_caps.append((f'{feature}:user:{user.pk}', user_cap))
        allowed = _fallback.consume(day, local_caps)
        logger.warning('ai_budget_cache_down feature=%s allowed=%s: using the per-process allowance', feature, allowed)
        return Reservation('process', day, [key for key, _ in local_caps]) if allowed else False
    if all(limit is None or count <= limit for count, (_, limit) in zip(counts, counters)):
        return Reservation('cache', day, [key for key, _ in counters])
    for key, _ in counters:
        cache_decrement(key)
    _note([f'{prefix}:refused'])
    return False


def refund(reservation):
    """Give back the call a :class:`Reservation` counted (the provider did not charge).

    Undoes only that backend, those keys and that day. Best effort; a falsy
    reservation (refused call) or one that counted nothing is a no-op.
    """
    if not reservation or reservation.backend is None:
        return
    if reservation.backend == 'cache':
        for key in reservation.keys:
            cache_decrement(key)
    else:
        _fallback.refund(reservation.day, reservation.keys)


def user_remaining(feature, user):
    """Calls ``user`` may still make today, or ``None`` (no per-user cap, or the cache cannot be read).

    Read-only and one cache read: nothing is incremented.
    """
    user_cap = _limits(feature)[2]
    if user_cap is None:
        return None
    key = f'ai-budget:{feature}:{timezone.localdate().isoformat()}:user:{user.pk}'
    values = cache_get_many([key])
    if values is None:
        return None
    return max(0, user_cap - int(values.get(key) or 0))


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
    """Whether this process still holds fallback-counted calls today (cache was unreachable).

    Those calls never reached the shared counters, so today's totals undercount. A call that was
    refunded leaves nothing behind, so it does not raise the flag.
    """
    return _fallback.day == timezone.localdate().isoformat() and any(_fallback.counts.values())


# -- Daily token caps for the assistant (no database: cache counters only) -----

class _TokenFallback:
    """Per-process daily token counters used only while the shared cache is down."""

    def __init__(self):
        self.lock = threading.Lock()
        self.day = None
        self.counts = {}

    def used(self, day, key):
        with self.lock:
            if day != self.day:
                self.day, self.counts = day, {}
            return self.counts.get(key, 0)

    def add(self, day, keys, tokens):
        with self.lock:
            if day != self.day:
                self.day, self.counts = day, {}
            for key in keys:
                self.counts[key] = self.counts.get(key, 0) + tokens


_token_fallback = _TokenFallback()


def _token_keys(user):
    day = timezone.localdate().isoformat()
    prefix = f'ai-tokens:assistant:{day}'
    return day, prefix, f'{prefix}:user:{user.pk}'


def tokens_available(user):
    """False when today's per-user or platform token cap is already used up.

    Read-only. ``0`` for a cap means no cap. A cache outage falls back to this
    process's own counters, so spend stays bounded per process.
    """
    user_cap = settings.AI_ASSISTANT_USER_DAILY_TOKENS
    global_cap = settings.AI_ASSISTANT_DAILY_TOKENS
    if not user_cap and not global_cap:
        return True
    day, global_key, user_key = _token_keys(user)
    values = cache_get_many([global_key, user_key])
    if values is None:
        used_global = _token_fallback.used(day, global_key)
        used_user = _token_fallback.used(day, user_key)
    else:
        used_global = int(values.get(global_key) or 0)
        used_user = int(values.get(user_key) or 0)
    if global_cap and used_global >= global_cap:
        _note([f'ai-budget:assistant:{day}:refused'])
        return False
    if user_cap and used_user >= user_cap:
        _note([f'ai-budget:assistant:{day}:refused'])
        return False
    return True


def add_tokens(user, tokens):
    """Add the tokens a finished call actually used. Never raises."""
    tokens = int(tokens or 0)
    if tokens <= 0 or not (settings.AI_ASSISTANT_USER_DAILY_TOKENS or settings.AI_ASSISTANT_DAILY_TOKENS):
        return
    day, global_key, user_key = _token_keys(user)
    results = [cache_add_amount(key, tokens, TTL_SECONDS) for key in (global_key, user_key)]
    if any(result is None for result in results):
        _token_fallback.add(day, (global_key, user_key), tokens)


def consume_job(feature):
    """Count one paid call made by a scheduled job (no user); ``False`` when the daily cap is reached.

    Otherwise returns a truthy :class:`Reservation` to hand to :func:`refund`, so a refund undoes the very
    counter that took the call even if the cache came back (or went down) in between.

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
        key = f'{feature}:process'
        allowed = _fallback.consume(day, [(key, local_cap)])
        logger.warning('ai_budget_cache_down feature=%s allowed=%s: using the per-process allowance', feature, allowed)
        return Reservation('process', day, [key]) if allowed else False
    if counts[0] <= cap:
        return Reservation('cache', day, [prefix])
    cache_decrement(prefix)
    _note([f'{prefix}:refused'])
    return False


def refund_job(feature, reservation=None):
    """Give back one call counted by :func:`consume_job` whose provider call failed.

    Pass the reservation ``consume_job`` returned: it undoes exactly that backend. Without one the backend is
    guessed from whether the cache is reachable now, which can pick the wrong counter after an outage.
    """
    if reservation:
        refund(reservation)
        return
    day = timezone.localdate().isoformat()
    prefix = f'ai-budget:{feature}:{day}'
    if cache_get_many([prefix]) is None:
        with _fallback.lock:
            key = f'{feature}:process'
            if _fallback.day == day and _fallback.counts.get(key):
                _fallback.counts[key] -= 1
        return
    cache_decrement(prefix)
