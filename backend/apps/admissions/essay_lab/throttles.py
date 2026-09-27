"""Essay Lab guards, built on the shared O(1) window throttles (apps.users.throttles).

Autosave has its own generous per-user limit instead of the general API rate,
and the Coach has a minimum interval plus an hourly cap. Fixed windows keep the
minimum interval exact.
"""

from django.conf import settings

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


def spend_coach_budget(user):
    """Count one AI depth check against the daily budgets. False when one is spent."""
    return ai_budget.consume('essay_coach', user)
