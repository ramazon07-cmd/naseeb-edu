from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .localization import localized_message


class VersionedJWTAuthentication(JWTAuthentication):
    password_change_paths = {
        '/api/users/accounts/me/',
        '/api/users/accounts/change-password/',
    }

    def authenticate(self, request):
        result = super().authenticate(request)
        if not result:
            return None
        user, token = result
        if token.get('pv') != user.password_version:
            raise InvalidToken({
                'detail': localized_message('session_revoked', request),
                'code': 'session_revoked',
            })
        if user.must_change_password and request.path_info not in self.password_change_paths:
            raise PermissionDenied({
                'detail': localized_message('password_change_required', request),
                'code': 'password_change_required',
            })
        return user, token


class VersionedJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Describe the custom, password-version-aware JWT authenticator in OpenAPI."""

    target_class = 'apps.users.authentication.VersionedJWTAuthentication'
    name = 'jwtAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
