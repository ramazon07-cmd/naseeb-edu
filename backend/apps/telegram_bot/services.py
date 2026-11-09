import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.admissions.scoping import is_locked_out_by_school
from apps.users.cache_safety import cache_delete_many, cache_get, count_hit
from apps.users.security import (
    login_locked, note_account_failure, register_login_failure, reset_login_failures,
)
from apps.users.throttles import hashed

from . import conf
from .digest import tashkent_now
from .models import DEFAULT_PREFS, PendingLogin, TelegramLink

User = get_user_model()

ALLOWED_ROLES = (User.Role.COUNSELOR, User.Role.ASSISTANT)
PENDING_TTL = timedelta(minutes=10)
CLAIM_LEASE = timedelta(minutes=2)
DUE_BATCH = 500
LANGUAGES = {choice for choice, _ in TelegramLink.Language.choices}
PREF_KEYS = frozenset(DEFAULT_PREFS)


class Refused(Exception):
    def __init__(self, code, status=403, **extra):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


def fingerprint(user):
    return hmac.new(settings.SECRET_KEY.encode(), user.password.encode(), hashlib.sha256).hexdigest()


def _account_error(user):
    """Why ``user`` may not use the bot, or ``None``. One rule for login, confirm and every later call."""
    if not user.is_active or user.is_product_admin or user.role not in ALLOWED_ROLES:
        return 'role_not_allowed'
    if is_locked_out_by_school(user):
        return 'account_unavailable'
    if user.role == User.Role.ASSISTANT:
        boss = user.supervising_counselor
        if boss is None or not boss.is_active or boss.role != User.Role.COUNSELOR:
            return 'account_unavailable'
    return None


def _attempt_keys(chat_id, account):
    return f'tgbot-login:chat:{chat_id}', f'tgbot-login:user:{hashed(account)}'


def _locked(keys):
    return any((cache_get(key) or 0) >= conf.LOGIN_MAX_ATTEMPTS for key in keys)


def _web_lockout_keys(chat_id, account):
    # Same counters and thresholds as the website login. The bot has no client IP, so a
    # per-chat and a bot-wide pseudo address stand in; web addresses are never locked by the bot.
    return (('user-ip', f'{account}|telegram:{chat_id}'), ('user-ip', f'{account}|telegram'))


def _resolve_login(login_value):
    """(username to authenticate, canonical account key); an email shared by several users resolves to nothing."""
    if '@' not in login_value:
        return login_value, login_value.lower()
    matches = list(User.objects.filter(email__iexact=login_value)[:2])
    if len(matches) == 1:
        username = matches[0].get_username()
        return username, username.lower()
    return None, login_value.lower()


def login(chat_id, login_value, password):
    login_value = login_value.strip()
    username, account = _resolve_login(login_value)
    keys = _attempt_keys(chat_id, account)
    web_keys = _web_lockout_keys(chat_id, account)
    if _locked(keys) or login_locked(*web_keys):
        raise Refused('locked', 429, retry_after=conf.LOGIN_WINDOW_SECONDS)
    user = authenticate(username=username, password=password) if username else None
    if user is None:
        for key in keys:
            count_hit(key, conf.LOGIN_WINDOW_SECONDS)
        register_login_failure(*web_keys)
        note_account_failure(account)
        raise Refused('invalid_credentials', 401)
    cache_delete_many(keys)
    reset_login_failures(*web_keys)
    user = User.objects.select_related('school', 'supervising_counselor').get(pk=user.pk)
    error = _account_error(user)
    if error:
        raise Refused(error)
    if user.must_change_password:
        raise Refused('password_change_required')
    token = secrets.token_urlsafe(32)
    PendingLogin.objects.update_or_create(chat_id=chat_id, defaults={
        'user': user,
        'token_hash': hashlib.sha256(token.encode()).hexdigest(),
        'auth_fingerprint': fingerprint(user),
        'expires_at': timezone.now() + PENDING_TTL,
    })
    return {
        'pending_token': token,
        'full_name': user.get_full_name().strip() or user.username,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
    }


def confirm(chat_id, token, language):
    pending = PendingLogin.objects.select_related(
        'user__school', 'user__supervising_counselor',
    ).filter(chat_id=chat_id, token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if pending is None or pending.expires_at <= timezone.now():
        raise Refused('pending_expired', 410)
    user = pending.user
    if _account_error(user) or fingerprint(user) != pending.auth_fingerprint:
        pending.delete()
        raise Refused('pending_expired', 410)
    try:
        with transaction.atomic():
            # One chat <-> one account: the newest login replaces any earlier link either way.
            TelegramLink.objects.filter(Q(chat_id=chat_id) | Q(user=user)).delete()
            link = TelegramLink.objects.create(
                user=user, chat_id=chat_id, language=language if isinstance(language, str) and language in LANGUAGES else 'uz',
                prefs=dict(DEFAULT_PREFS), auth_fingerprint=pending.auth_fingerprint,
            )
            pending.delete()
    except IntegrityError:
        raise Refused('pending_expired', 410)
    return link


def resolve_link(chat_id):
    """The chat's link while its account is still allowed to use the bot; otherwise wipe it."""
    link = TelegramLink.objects.select_related('user__school', 'user__supervising_counselor').filter(
        chat_id=chat_id,
    ).first()
    if link is None:
        raise Refused('not_linked', 404)
    if _account_error(link.user) or fingerprint(link.user) != link.auth_fingerprint:
        link.delete()
        raise Refused('not_linked', 404)
    return link


def unlink(chat_id):
    TelegramLink.objects.filter(chat_id=chat_id).delete()
    PendingLogin.objects.filter(chat_id=chat_id).delete()


def settings_payload(link):
    return {
        'full_name': link.user.get_full_name().strip() or link.user.username,
        'role': link.user.role,
        'language': link.language,
        'notify_time': link.notify_time.strftime('%H:%M') if link.notify_time else None,
        'prefs': {**DEFAULT_PREFS, **link.prefs},
        'enabled': link.is_active,
    }


def update_settings(link, *, language=None, notify_time=None, prefs=None, enabled=None, now=None):
    fields = []
    if language is not None:
        link.language = language
        fields.append('language')
    if notify_time is not None:
        link.notify_time = notify_time
        fields.append('notify_time')
        now = tashkent_now(now)
        if notify_time <= now.time().replace(second=0, microsecond=0):
            # A time that already passed today starts tomorrow, not with an instant send.
            link.last_sent_date = now.date()
            fields.append('last_sent_date')
    if prefs is not None:
        link.prefs = {**DEFAULT_PREFS, **link.prefs, **prefs}
        fields.append('prefs')
    if enabled is not None:
        link.is_active = enabled
        fields.append('is_active')
    if fields:
        link.save(update_fields=[*fields, 'updated_at'])
    return link


def due(now=None, limit=DUE_BATCH):
    """Chats whose update is due; each is leased so another instance skips it."""
    now = tashkent_now(now)
    grace = conf.DUE_GRACE_MINUTES
    slots = {}
    for k in range(grace + 1):
        slot = now - timedelta(minutes=k)
        slots.setdefault(slot.time().replace(second=0, microsecond=0), slot.date())
    when = Q()
    for slot_time, slot_date in slots.items():
        when |= Q(notify_time=slot_time) & ~Q(last_sent_date=slot_date)
    lease_start = timezone.now()
    with transaction.atomic():
        rows = list(
            TelegramLink.objects.select_for_update(skip_locked=True)
            .filter(when, is_active=True)
            .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lt=lease_start - CLAIM_LEASE))
            .order_by('id')[:limit]
        )
        TelegramLink.objects.filter(pk__in=[row.pk for row in rows]).update(claimed_at=lease_start)
    return [
        {'chat_id': row.chat_id, 'language': row.language, 'slot_date': slots[row.notify_time].isoformat()}
        for row in rows
    ]


def mark_sent(chat_id, slot_date):
    return TelegramLink.objects.filter(chat_id=chat_id).filter(
        Q(last_sent_date__isnull=True) | Q(last_sent_date__lt=slot_date),
    ).update(last_sent_date=slot_date, claimed_at=None)
