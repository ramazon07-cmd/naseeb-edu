from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from .admin_permissions import enforce_staff_write_scope
from .entitlements import loaded_school_is_read_only
from .localization import localized_message


def school_inactive_error(request):
    return AuthenticationFailed({
        'detail': localized_message('school_inactive', request),
        'code': 'school_inactive',
    })


class VersionedJWTAuthentication(JWTAuthentication):
    password_change_paths = {
        '/api/users/accounts/me/',
        '/api/users/accounts/change-password/',
    }

    def get_user(self, validated_token):
        # Same checks as simplejwt, but the tenant school and its subscription
        # are loaded in the same query, so the inactive-school and read-only
        # workspace checks cost no extra query.
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(_('Token contained no recognizable user identification')) from exc
        try:
            user = self.user_model.objects.select_related(
                'school__subscription', 'student_profile__school__subscription',
            ).get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except self.user_model.DoesNotExist as exc:
            raise AuthenticationFailed(_('User not found'), code='user_not_found') from exc
        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_('User is inactive'), code='user_inactive')
        if api_settings.CHECK_REVOKE_TOKEN and (
            validated_token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password)
        ):
            raise AuthenticationFailed(_("The user's password has been changed."), code='password_changed')
        return user

    def authenticate(self, request):
        from apps.admissions.scoping import is_locked_out_by_school, tenant_school

        result = super().authenticate(request)
        if not result:
            return None
        user, token = result
        if token.get('pv') != user.password_version:
            raise InvalidToken({
                'detail': localized_message('session_revoked', request),
                'code': 'session_revoked',
            })
        if is_locked_out_by_school(user):
            raise school_inactive_error(request)
        if user.must_change_password and request.path_info not in self.password_change_paths:
            raise PermissionDenied({
                'detail': localized_message('password_change_required', request),
                'code': 'password_change_required',
            })
        if request.method not in SAFE_METHODS:
            self.enforce_write_access(request, user, tenant_school(user))
        return user, token

    def enforce_write_access(self, request, user, school):
        # Every JWT-authenticated write passes here, so staff tiers and
        # read-only workspaces are enforced once instead of in every view.
        if request.path_info in self.password_change_paths:
            return
        enforce_staff_write_scope(request, user)
        if school is not None and not user.is_product_admin and loaded_school_is_read_only(school):
            raise PermissionDenied({
                'detail': localized_message('workspace_read_only', request),
                'code': 'workspace_read_only',
            })
