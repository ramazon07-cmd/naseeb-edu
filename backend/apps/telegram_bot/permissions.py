import hmac

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

HEADER = 'HTTP_X_BOT_SERVICE_KEY'


class AuthRejected(AuthenticationFailed):
    default_detail = 'Unauthorized.'


class HasServiceKey(BasePermission):
    """Shared-secret check; a missing, empty or wrong key is a bare 401."""

    def has_permission(self, request, view):
        expected = (settings.BOT_SERVICE_KEY or '').encode('utf-8')
        given = request.META.get(HEADER, '').encode('utf-8')
        if not expected or not hmac.compare_digest(expected, given):
            raise AuthRejected()
        return True
