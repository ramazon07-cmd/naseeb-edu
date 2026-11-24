import uuid

import jwt
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.db import OperationalError, ProgrammingError, transaction
from django.db.models import F, Q
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.users.throttles import (
    LoginAccountCeilingThrottle, LoginAccountThrottle, LoginIPThrottle, RefreshIPThrottle, RefreshTokenThrottle,
)
from rest_framework_simplejwt.exceptions import ExpiredTokenError, InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .auth_cookies import (
    clear_refresh_cookie, enforce_cookie_csrf, enforce_login_origin, move_refresh_to_cookie, refresh_cookie,
)
from .credentials import mark_temporary_credential_used
from .models import RefreshRotation, RevokedRefreshSession
from .localization import localized_message
from .security import (
    client_ip, login_locked, security_logger, note_account_failure, register_login_failure, remember_login_device, reset_login_failures,
)


# last_login is "last seen signed in": a password sign-in or a session refresh
# (every 30 minutes while a tab is open). Written at most once per window, so an
# open tab costs one small UPDATE an hour.
LAST_LOGIN_WINDOW = timedelta(hours=1)


def note_sign_in(user_id, now=None):
    now = now or timezone.now()
    get_user_model().objects.filter(pk=user_id).filter(
        Q(last_login__isnull=True) | Q(last_login__lt=now - LAST_LOGIN_WINDOW),
    ).update(last_login=now)


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """JWT login that accepts username OR email.

    For local demo reliability, the demo counselor account is repaired automatically
    when the expected local credentials are used.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['pv'] = user.password_version
        # One id per sign-in, kept by every rotation: logout revokes the chain.
        token['sid'] = uuid.uuid4().hex
        token['must_change_password'] = user.must_change_password
        return token

    def validate(self, attrs):
        User = get_user_model()
        login_value = str(attrs.get(self.username_field, '')).strip()
        password = attrs.get('password')

        try:
            # If the demo user was not seeded or password was accidentally changed,
            # repair it so the downloaded project logs in first try.
            if (
                settings.DEMO_ACCOUNTS_ENABLED
                and login_value in {'counselor', 'counselor@naseeb.local'}
                and password == settings.DEMO_COUNSELOR_PASSWORD
            ):
                from apps.admissions.models import School
                demo_school, _ = School.objects.get_or_create(
                    code='naseeb-edu-demo',
                    defaults={'name': 'Naseeb Edu Demo School'},
                )
                user, _ = User.objects.get_or_create(
                    username='counselor',
                    defaults={
                        'email': 'counselor@naseeb.local',
                        'first_name': 'Firdavs',
                        'last_name': 'Counselor',
                        'role': 'counselor',
                        'is_staff': True,
                        'school': demo_school,
                    },
                )
                user.email = user.email or 'counselor@naseeb.local'
                user.role = 'counselor'
                user.is_staff = True
                user.school = demo_school
                user.set_password(settings.DEMO_COUNSELOR_PASSWORD)
                user.save()
                attrs[self.username_field] = 'counselor'
                return super().validate(attrs)

            if '@' in login_value:
                user = User.objects.filter(email__iexact=login_value).first()
                if user:
                    attrs[self.username_field] = getattr(user, self.username_field)
        except (OperationalError, ProgrammingError):
            # Migrations have not been applied yet. Let the normal serializer return
            # a clean auth error instead of hiding the real setup mistake.
            pass

        # Lockout keyed on (account, client IP): repeated failures lock that
        # account *from that address* only, so an attacker cannot lock the real
        # owner out from elsewhere.
        request = self.context.get('request')
        client = client_ip(request) if request is not None else ''
        account = str(attrs.get(self.username_field) or login_value).strip().lower()
        lockout_key = ('user-ip', f'{account}|{client}')
        if login_locked(lockout_key):
            raise Throttled(wait=settings.LOGIN_LOCKOUT_WINDOW_SECONDS)
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            register_login_failure(lockout_key)
            note_account_failure(account)
            raise
        reset_login_failures(lockout_key)
        # Lets this address skip the account-wide login ceiling next time.
        remember_login_device((login_value, self.user.get_username(), self.user.email), client)
        from apps.admissions.scoping import is_locked_out_by_school
        from .authentication import school_inactive_error

        if is_locked_out_by_school(self.user):
            raise school_inactive_error(request)
        if self.user.must_change_password:
            credential, error_key = mark_temporary_credential_used(user=self.user, request=self.context.get('request'))
            if error_key:
                raise AuthenticationFailed({
                    'detail': localized_message(error_key, self.context.get('request')),
                    'code': error_key,
                })
            data['credential_expires_at'] = credential.expires_at
        note_sign_in(self.user.pk)
        data['must_change_password'] = self.user.must_change_password
        data['role'] = self.user.role
        return data


def token_pair_for_user(user):
    refresh = EmailOrUsernameTokenSerializer.get_token(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


class DemoAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer
    # Per (account, IP) rather than per IP: a class signing in together from
    # one school IP must not share a single allowance.
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle, LoginAccountCeilingThrottle]

    def post(self, request, *args, **kwargs):
        enforce_login_origin(request)
        return move_refresh_to_cookie(super().post(request, *args, **kwargs))


# A grace window never hands out more than this many pairs per rotated token.
MAX_GRACE_REUSES = 2


def _is_expired(exc):
    return isinstance(exc, ExpiredTokenError) or 'expired' in str(exc).lower()


class SafeTokenRefreshSerializer(TokenRefreshSerializer):
    """Return a normal auth failure when a refresh token's user was deleted.

    Rotation: the presented token is blacklisted and a new one issued. The
    exchange is recorded (RefreshRotation) so that the same token, presented
    again within AUTH_REFRESH_REUSE_GRACE_SECONDS (a second tab, a retry after
    a lost response), gets a fresh pair of the same session instead of a 401.

    `reason` / `info` say why a refresh was refused, for the view's log line."""

    reason = None
    info = None

    def refuse(self, reason, error, **info):
        self.reason = reason
        self.info = info
        raise error

    def validate(self, attrs):
        raw = attrs['refresh']
        try:
            token = UntypedToken(raw)  # signature and expiry, blacklisted or not
        except TokenError as exc:
            self.refuse('expired' if _is_expired(exc) else 'invalid', exc)
        if token.get('token_type') != 'refresh':
            self.refuse('invalid', TokenError('Token has wrong type'))
        sid, jti = token.get('sid'), token.get('jti')
        if sid and RevokedRefreshSession.objects.filter(sid=sid).exists():
            self.refuse('revoked_session', InvalidToken({'detail': 'This session was signed out.', 'code': 'token_not_valid'}))
        try:
            with transaction.atomic():
                data = super().validate(attrs)
                if sid and jti:
                    _, created = RefreshRotation.objects.get_or_create(
                        old_jti=jti,
                        defaults={'sid': sid, 'user_id': token.get(api_settings.USER_ID_CLAIM) or 0},
                    )
                    if not created and not RefreshRotation.objects.filter(
                        old_jti=jti, reuses__lt=MAX_GRACE_REUSES,
                    ).update(reuses=F('reuses') + 1):
                        # Another worker rotated this token between our blacklist
                        # check and now: that issuance counts against the cap,
                        # and is refused (and rolled back) once the cap is spent.
                        raise TokenError('Token is blacklisted')
                return data
        except get_user_model().DoesNotExist as exc:
            self.refuse('no_active_account', AuthenticationFailed({
                'detail': self.error_messages['no_active_account'],
                'code': 'no_active_account',
            }), user_missing=True)
        except AuthenticationFailed:
            self.reason = 'no_active_account'
            raise
        except TokenError as exc:
            if str(exc) != 'Token is blacklisted':
                self.refuse('expired' if _is_expired(exc) else 'invalid', exc)
            pair = self.grace_pair(token, sid, jti)
            if pair is not None:
                return pair
            raise

    def grace_pair(self, token, sid, jti):
        """A fresh pair for a token rotated moments ago, or None (-> 401)."""
        self.reason = 'blacklisted'
        grace = int(getattr(settings, 'AUTH_REFRESH_REUSE_GRACE_SECONDS', 0) or 0)
        row = RefreshRotation.objects.filter(old_jti=jti).first() if (sid and jti) else None
        if row is None:
            self.info = {'rotation_record': False}
            return None
        age = (timezone.now() - row.rotated_at).total_seconds()
        self.info = {'rotation_record': True, 'rotated_seconds_ago': int(age), 'grace_seconds': grace}
        if grace <= 0 or age > grace or row.sid != sid or row.reuses >= MAX_GRACE_REUSES:
            return None
        user = get_user_model().objects.filter(pk=row.user_id).first()
        if (
            user is None
            or not api_settings.USER_AUTHENTICATION_RULE(user)
            or token.get('pv') != user.password_version
        ):
            self.reason = 'no_active_account'
            return None
        if RevokedRefreshSession.objects.filter(sid=sid).exists():
            self.reason = 'revoked_session'
            return None
        with transaction.atomic():
            # Claim a slot atomically: concurrent requests cannot both pass the cap.
            claimed = RefreshRotation.objects.filter(pk=row.pk, reuses__lt=MAX_GRACE_REUSES).update(reuses=F('reuses') + 1)
            if claimed != 1:
                return None
            fresh = RefreshToken()
            for claim, value in token.payload.items():
                if claim not in {'exp', 'iat', 'jti', 'token_type'}:
                    fresh[claim] = value
            fresh.outstand()
        self.reason = 'grace_reuse'
        security_logger.info('refresh token reused inside the grace window: user=%s rotated_seconds_ago=%d', row.user_id, age)
        return {'access': str(fresh.access_token), 'refresh': str(fresh)}


def signed_user_id(token):
    """The user id of a token whose signature is valid (an expired one is fine),
    as an int; None for anything forged, malformed or non-numeric, so a log line
    can never carry attacker-chosen text."""
    try:
        payload = jwt.decode(
            token, token_backend.get_verifying_key(token), algorithms=[token_backend.algorithm],
            options={'verify_exp': False, 'verify_aud': False},
        )
        return int(payload.get(api_settings.USER_ID_CLAIM))
    except Exception:
        return None


class SafeTokenRefreshView(TokenRefreshView):
    serializer_class = SafeTokenRefreshSerializer
    # Not the per-IP anonymous rate: every tab behind a shared IP refreshes.
    throttle_classes = [RefreshIPThrottle, RefreshTokenThrottle]

    def refusal(self, request, reason, token=None, **info):
        """One log line per refused refresh: the reason and the user if known.
        Never the token. The user id is read from the signed token (which can
        be expired or blacklisted) and is absent for malformed ones."""
        user_id = signed_user_id(token) if token else None
        extra = ' '.join(f'{key}={value}' for key, value in info.items())
        security_logger.warning(
            'refresh refused: reason=%s user=%s ip=%r ua=%r %s',
            reason, user_id if user_id is not None else 'unknown', client_ip(request),
            (request.headers.get('User-Agent') or '')[:80], extra,
        )

    def post(self, request, *args, **kwargs):
        # The token comes only from the HttpOnly cookie; a body field is ignored.
        enforce_cookie_csrf(request)
        token = refresh_cookie(request)
        if not token:
            self.refusal(request, 'missing_cookie')
            raise InvalidToken({'detail': 'No refresh token cookie.', 'code': 'token_not_valid'})
        serializer = self.get_serializer(data={'refresh': token})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, AuthenticationFailed) as exc:
            self.refusal(request, serializer.reason or 'invalid', token, **(serializer.info or {}))
            if isinstance(exc, TokenError):
                raise InvalidToken(exc.args[0]) from exc
            raise
        user_id = UntypedToken(token).payload.get(api_settings.USER_ID_CLAIM)
        if user_id is not None:
            note_sign_in(user_id)
        return move_refresh_to_cookie(Response(serializer.validated_data, status=status.HTTP_200_OK))


def revoke_refresh_token(token):
    """Revoke the sign-in session `token` belongs to, and blacklist the token.

    Works for a token that was already rotated (blacklisted): its session id
    still revokes the newer tokens of the same chain."""
    if not token:
        return
    try:
        payload = UntypedToken(token).payload  # signature and expiry; blacklisted or not
    except TokenError:
        return  # malformed or expired: nothing can be refreshed with it
    if payload.get('token_type') != 'refresh':
        return
    if payload.get('sid'):
        # A refresh that passed its check just before this can still issue one
        # more token of the chain; keep the row a day longer than that token.
        lifetime = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] + timedelta(days=1)
        RevokedRefreshSession.objects.get_or_create(
            sid=payload['sid'], defaults={'expires_at': timezone.now() + lifetime},
        )
    try:
        RefreshToken(token).blacklist()
    except TokenError:
        pass  # already blacklisted by a rotation; the session row covers its successors


class LogoutView(APIView):
    """Revoke this browser's session and clear its cookie.

    Needs no access token: signing out must work after it expired.

    One-time migration: the previous frontend kept refresh tokens in
    localStorage. It posts such a token as {"refresh": ...}; that token is
    revoked and the cookie (which may belong to a newer sign-in) is left alone.
    The CSRF header and Origin are required either way."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    # Not throttled: a 429 here would skip the blacklist and leave a working
    # cookie on a shared computer. Without a valid cookie it costs no write.
    throttle_classes = []

    def post(self, request):
        enforce_cookie_csrf(request)
        legacy = request.data.get('refresh') if isinstance(request.data, dict) else None
        if isinstance(legacy, str) and legacy.strip():
            revoke_refresh_token(legacy.strip())
            return Response(status=status.HTTP_204_NO_CONTENT)
        revoke_refresh_token(refresh_cookie(request))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response
