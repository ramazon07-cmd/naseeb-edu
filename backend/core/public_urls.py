"""The one public address of the NaseebEdu web app, for every link sent to a person.

Telegram messages, emails, invitations and meeting links must be built with
``public_url`` (backed by ``settings.FRONTEND_URL``), never from the incoming
request host: behind Render the request host can be an internal address.
"""
import ipaddress
from urllib.parse import urlsplit

from django.conf import settings


def public_url(path=''):
    """The public site address plus ``path`` (e.g. ``/login``)."""
    base = str(settings.FRONTEND_URL).rstrip('/')
    if not path:
        return base
    return base + (path if path.startswith(('/', '?')) else '/' + path)


def frontend_url_problems(url):
    """Why ``url`` can't be the public site address (empty list when it can)."""
    parts = urlsplit(str(url or '').strip())
    host = (parts.hostname or '').lower()
    if parts.scheme != 'https':
        return ['it must start with https://']
    if not host:
        return ['it has no host name']
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.onrender.internal')):
        return [f'{host} is a local or internal name']
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A bare single-label name (e.g. "web") is only reachable inside a private network.
        return [] if '.' in host else [f'{host} is not a public domain name']
    return [f'{host} is an IP address, not the public domain name']
