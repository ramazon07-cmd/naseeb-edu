"""Constant-cost rate limits shared by the whole API.

DRF's SimpleRateThrottle stores a list of request timestamps per client and
rewrites it on every request: up to 1,200 entries per user for the default
rate, read, trimmed and written back each time. These throttles keep one
integer counter per time window instead, updated with a single atomic cache
round trip, so a check is O(1) whatever the rate.

``sliding`` throttles (the default) weight the previous window's count by how
much of it still overlaps the last ``window`` seconds (the "sliding window
counter"), which avoids the double burst a plain fixed window allows at its
boundary. ``sliding = False`` gives a fixed window, which suits minimum-interval
limits such as "one request per 15 s".

Rates use DRF's format (``'1200/hour'``) and ``DEFAULT_THROTTLE_RATES``.
Rejected requests are not counted, and every cache error fails open.
"""

import hashlib
import math
import time

from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import BaseThrottle

from .cache_safety import cache_decrement, count_hit
from .security import client_ip, is_known_login_device

PERIODS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


def parse_rate(rate):
    """``'1200/hour'`` -> ``(1200, 3600)``; ``None`` -> ``None``."""
    if not rate:
        return None
    num, period = str(rate).split('/')
    return int(num), PERIODS[period.strip()[0]]


def hashed(value):
    """A short stable digest, so raw identifiers (tokens, emails) never become cache keys."""
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:32]


def _retry_after(limit, window, elapsed, current, previous, sliding):
    """Seconds until one more request fits, given the counts before this request."""
    remaining = window - elapsed
    if not sliding or limit <= 0:
        return remaining
    if current + 1 <= limit and previous:
        # Wait until the previous window's weight has decayed enough.
        return (1 - (limit - current - 1) / previous) * window - elapsed
    # The current window is full: in the next one it becomes the previous.
    return remaining + max(0.0, 1 - (limit - 1) / current) * window if current else remaining


class WindowRateThrottle(BaseThrottle):
    scope = None
    sliding = True
    cache_prefix = 'throttle'

    def get_rate(self):
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError as exc:
            raise ImproperlyConfigured(f"No default throttle rate set for '{self.scope}' scope") from exc

    def get_limits(self):
        """Return ``[(max_requests, window_seconds), ...]``; a window of 0 turns a limit off."""
        parsed = parse_rate(self.get_rate())
        return [parsed] if parsed else []

    def get_ident(self, request):
        return client_ip(request)

    def get_cache_key(self, request, view):
        """The identity to count requests for, or ``None`` to skip this throttle."""
        raise NotImplementedError

    def allow_request(self, request, view):
        self.wait_seconds = None
        ident = self.get_cache_key(request, view)
        if ident is None:
            return True
        now = time.time()
        counted = []
        for limit, window in self.get_limits():
            if window <= 0:
                continue
            bucket = int(now // window)
            key = f'{self.cache_prefix}:{self.scope}:{ident}:{window}:{bucket}'
            previous_key = f'{self.cache_prefix}:{self.scope}:{ident}:{window}:{bucket - 1}' if self.sliding else None
            result = count_hit(key, (2 if self.sliding else 1) * window + 5, also_read=previous_key)
            if result is None:  # cache down: fail open
                continue
            current, previous = result
            elapsed = now - bucket * window
            if current + previous * (window - elapsed) / window <= limit:
                counted.append(key)
                continue
            for undo in (key, *counted):
                cache_decrement(undo)
            wait = _retry_after(limit, window, elapsed, current - 1, previous, self.sliding)
            self.wait_seconds = max(1, math.ceil(wait))
            return False
        return True

    def wait(self):
        return self.wait_seconds


class UserRateThrottle(WindowRateThrottle):
    """Per signed-in user (``'user'`` rate). Anonymous requests are left to AnonRateThrottle."""

    scope = 'user'

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        return str(user.pk) if user is not None and user.is_authenticated else None


class AnonRateThrottle(WindowRateThrottle):
    """Per client IP for anonymous requests (``'anon'`` rate)."""

    scope = 'anon'

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return None
        return self.get_ident(request)


class ScopedRateThrottle(WindowRateThrottle):
    """The view's ``throttle_scope``, counted per user (or per IP when anonymous)."""

    def allow_request(self, request, view):
        self.scope = getattr(view, 'throttle_scope', None)
        if not self.scope:
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return f'user:{user.pk}'
        return f'ip:{self.get_ident(request)}'


def _body_field(request, name):
    data = request.data
    value = data.get(name) if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else ''


class IPCeilingThrottle(WindowRateThrottle):
    """A generous per-IP ceiling. A whole school or a carrier NAT can share one
    address, so this only stops floods; the real limit is per account/token."""

    def get_cache_key(self, request, view):
        return self.get_ident(request)


class LoginIPThrottle(IPCeilingThrottle):
    scope = 'login_ip'


def _login_account(request):
    from django.contrib.auth import get_user_model

    return _body_field(request, get_user_model().USERNAME_FIELD).lower()


class LoginAccountThrottle(WindowRateThrottle):
    """Sign-in attempts per (account, client IP), matching the lockout, so
    guesses from other addresses never use up the owner's allowance."""

    scope = 'login'

    def get_cache_key(self, request, view):
        account = _login_account(request)
        return hashed(f'{account}|{self.get_ident(request)}') if account else None


class LoginAccountCeilingThrottle(WindowRateThrottle):
    """A high account-wide ceiling that slows guessing spread over many IPs.

    Addresses that already signed in to the account skip it, so an attacker
    can slow new devices down but never keep the owner out."""

    scope = 'login_account'

    def get_cache_key(self, request, view):
        account = _login_account(request)
        if not account or is_known_login_device(account, self.get_ident(request)):
            return None
        return hashed(account)


class RefreshIPThrottle(IPCeilingThrottle):
    scope = 'refresh_ip'


class RefreshTokenThrottle(WindowRateThrottle):
    """Refresh attempts per refresh token. Keyed on the token itself rather than
    its (unverified) user id, so nobody can spend another user's allowance."""

    scope = 'refresh'

    def get_cache_key(self, request, view):
        token = _body_field(request, 'refresh')
        return hashed(token) if token else None
