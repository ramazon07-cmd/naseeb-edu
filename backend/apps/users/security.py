"""Request-origin and brute-force helpers shared by the API and admin logins."""
import hashlib
import logging
from functools import wraps

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound

from .cache_safety import cache_delete_many, cache_get, cache_increment, cache_set_many


def num_proxies():
    return settings.REST_FRAMEWORK.get('NUM_PROXIES')


def client_ip(request):
    """Return the client address, trusting only ``NUM_PROXIES`` hops of X-Forwarded-For.

    Mirrors ``rest_framework.throttling.BaseThrottle.get_ident`` so the login
    throttle, lockout and audit metadata all agree on who the client is, and a
    client-supplied X-Forwarded-For cannot pick its own IP.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '')
    proxies = num_proxies()
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if proxies and xff:
        addresses = [part.strip() for part in xff.split(',') if part.strip()]
        if addresses:
            return addresses[-min(proxies, len(addresses))]
    return remote_addr


security_logger = logging.getLogger('naseeb.security')


def _key(scope, value):
    return f'login-fail:{scope}:{str(value or "").strip().lower()[:200]}'


def login_locked(*identifiers):
    threshold = settings.LOGIN_LOCKOUT_THRESHOLD
    return any((cache_get(_key(scope, value)) or 0) >= threshold for scope, value in identifiers if value)


def register_login_failure(*identifiers):
    timeout = settings.LOGIN_LOCKOUT_WINDOW_SECONDS
    for scope, value in identifiers:
        if value:
            cache_increment(_key(scope, value), timeout)


def reset_login_failures(*identifiers):
    cache_delete_many([_key(scope, value) for scope, value in identifiers if value])


def guarded_admin_login(login_view):
    """Wrap ``admin.site.login`` with the same lockout the API login uses."""

    @wraps(login_view)
    def view(request, *args, **kwargs):
        if request.method != 'POST':
            return login_view(request, *args, **kwargs)
        address = client_ip(request)
        identifiers = (
            # Account+IP, so a victim is never locked out from their own address,
            # plus a per-IP cap because the admin form has no DRF throttle.
            ('admin-user-ip', f"{request.POST.get('username', '').strip().lower()}|{address}"),
            ('admin-ip', address),
        )
        if login_locked(*identifiers):
            return HttpResponse('Too many failed login attempts. Try again later.', status=429)
        response = login_view(request, *args, **kwargs)
        if response.status_code == 302:
            reset_login_failures(identifiers[0])
        else:
            register_login_failure(*identifiers)
        return response

    return view


class AdminIPAllowlistMiddleware:
    """Hide ``/admin/`` from addresses outside ``ADMIN_ALLOWED_IPS`` (when configured)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = settings.ADMIN_ALLOWED_IPS
        if allowed and request.path_info.startswith('/admin/') and client_ip(request) not in allowed:
            return HttpResponseNotFound()
        return self.get_response(request)


def note_account_failure(account):
    """Count failures per account across all IPs, for detection only.

    The lockout is per (account, IP) so nobody can lock a victim out, which also
    means guesses spread over many IPs are never blocked per account. This
    counter doesn't block anything; it logs a security warning once an account
    crosses LOGIN_ACCOUNT_ALERT_THRESHOLD failures in a window, so distributed
    guessing is visible in the logs.
    """
    count = cache_increment(_key('user-any', account), settings.LOGIN_LOCKOUT_WINDOW_SECONDS)
    if count == settings.LOGIN_ACCOUNT_ALERT_THRESHOLD:
        security_logger.warning(
            'login_failures_spread_across_ips account=%s failures=%s window_seconds=%s',
            str(account)[:80], count, settings.LOGIN_LOCKOUT_WINDOW_SECONDS,
        )
    return count



def _device_key(account, address):
    digest = hashlib.sha256(f'{str(account or "").strip().lower()}|{address}'.encode('utf-8')).hexdigest()[:32]
    return f'login-device:{digest}'


def remember_login_device(accounts, address):
    """Remember that ``address`` signed in to these account names (username, email)."""
    names = {str(name).strip().lower() for name in accounts if name}
    if names and address:
        cache_set_many({_device_key(name, address): 1 for name in names}, settings.LOGIN_KNOWN_DEVICE_SECONDS)


def is_known_login_device(account, address):
    if not account or not address:
        return False
    return bool(cache_get(_device_key(account, address)))
