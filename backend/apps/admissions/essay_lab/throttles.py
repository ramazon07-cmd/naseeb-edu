"""Essay Lab guards, built on the shared O(1) window throttles (apps.users.throttles).

Autosave has its own generous per-user limit instead of the general API rate,
and the Coach has a minimum interval plus an hourly cap. Fixed windows keep the
minimum interval exact.
"""

from django.conf import settings
from django.utils import timezone

from apps.users.cache_safety import count_hits
from apps.users.throttles import WindowRateThrottle

from .. import ai_budget


class EssayThrottle(WindowRateThrottle):
    sliding = False
    cache_prefix = 'essay-lab'

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        return str(user.pk) if user is not None and user.is_authenticated else None


class EssayAutosaveThrottle(EssayThrottle):
    scope = 'essay_autosave'

    def get_limits(self):
        return [(settings.ESSAY_AUTOSAVE_LIMIT, settings.ESSAY_AUTOSAVE_WINDOW_SECONDS)]


class EssayDepthCheckThrottle(EssayThrottle):
    scope = 'essay_depth_check'

    def get_limits(self):
        return [
            (1, settings.ESSAY_COACH_MIN_INTERVAL_SECONDS),
            (settings.ESSAY_COACH_HOURLY_LIMIT, 3600),
        ]


class EssayDepthGateThrottle(EssayThrottle):
    """Cheap per-user limit in front of the re-check rules; spends neither the check interval nor the budget."""

    scope = 'essay_depth_gate'

    def get_limits(self):
        return [(settings.ESSAY_COACH_RECHECK_PER_MINUTE, 60)]


def spend_coach_budget(user):
    """Count one AI depth check against the daily budgets: a Reservation (to refund), or False when one is spent."""
    return ai_budget.consume('essay_coach', user)


SAFETY_FREE_TTL_SECONDS = 26 * 60 * 60


def take_free_safety_check(user):
    """Whether a check that ended in the safety message is free for ``user``: the first
    ESSAY_SAFETY_FREE_PER_DAY of each day are, later ones count like any check. Fails closed when the
    cache is down (not free), so this path cannot be used for free checks."""
    limit = settings.ESSAY_SAFETY_FREE_PER_DAY
    if limit <= 0:
        return False
    counts = count_hits([f'essay-safety-free:{timezone.localdate().isoformat()}:{user.pk}'], SAFETY_FREE_TTL_SECONDS)
    return counts is not None and counts[0] <= limit
