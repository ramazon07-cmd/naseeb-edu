"""Connect a Google account: a verified email for meeting emails. Identity only, no Google API access."""
import base64
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .services import audit_product_action
from .throttles import ScopedRateThrottle

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
STATE_SALT = 'users.google-connect'
STATE_MAX_AGE = 600


def google_connect_enabled():
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def redirect_uri(request):
    return settings.GOOGLE_OAUTH_REDIRECT_URI or request.build_absolute_uri(reverse('google-callback'))


def exchange_code(code, callback):
    """The verified Google identity behind `code` as (sub, email), or None."""
    body = urlencode({
        'code': code, 'client_id': settings.GOOGLE_OAUTH_CLIENT_ID, 'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': callback, 'grant_type': 'authorization_code',
    }).encode()
    try:
        with urlopen(Request(TOKEN_URL, data=body), timeout=10) as response:  # noqa: S310 - fixed https URL
            id_token = json.load(response)['id_token']
        # Straight from Google over TLS, so the signature needs no second check; the claims still do.
        payload = id_token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (URLError, OSError, ValueError, KeyError, IndexError):
        return None
    if claims.get('aud') != settings.GOOGLE_OAUTH_CLIENT_ID or claims.get('email_verified') is not True:
        return None
    if not claims.get('sub') or not claims.get('email'):
        return None
    return str(claims['sub']), str(claims['email'])


class GoogleConnectStartView(APIView):
    """The signed-in user asks where to go to connect Google; the answer is bound to them for ten minutes."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'google_connect'

    def post(self, request):
        if not google_connect_enabled():
            return Response({'detail': 'Google sign-in is not set up yet.'}, status=503)
        state = signing.dumps({'u': request.user.pk, 'pv': request.user.password_version}, salt=STATE_SALT)
        query = urlencode({
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID, 'redirect_uri': redirect_uri(request), 'response_type': 'code',
            'scope': 'openid email', 'state': state, 'prompt': 'select_account',
        })
        return Response({'url': f'{AUTH_URL}?{query}'})


class GoogleConnectCallbackView(APIView):
    """Google sends the browser back here; there is no session, so the signed `state` names the user."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'google_connect'

    def get(self, request):
        def back(result):
            return HttpResponseRedirect(f'{settings.FRONTEND_URL}/meetings?google={result}')

        if not google_connect_enabled():
            return back('failed')
        try:
            state = signing.loads(request.query_params.get('state', ''), salt=STATE_SALT, max_age=STATE_MAX_AGE)
            user = User.objects.get(pk=state['u'], password_version=state['pv'], is_active=True)
        except (signing.BadSignature, User.DoesNotExist, KeyError, TypeError):
            return back('failed')
        identity = exchange_code(request.query_params.get('code', ''), redirect_uri(request))
        if not identity:
            return back('failed')
        user.google_sub, user.google_email = identity
        user.save(update_fields=['google_sub', 'google_email'])
        audit_product_action(actor=user, action='account.google_connected', target=user, school=user.school)
        return back('connected')
