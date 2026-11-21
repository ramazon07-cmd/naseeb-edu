"""Which Telegram users may use the counselor login in the bot (set by a superadmin on the website)."""
import re

from django.db import IntegrityError, transaction

from apps.users.models import User

from .models import StaffTelegramAccess
from .services import ALLOWED_ROLES, Refused

USERNAME_PATTERN = re.compile(r'^[a-z0-9_]{5,32}$')


def normalize_username(value):
    """Lowercase, without '@' or spaces; '' when empty."""
    return str(value or '').strip().lstrip('@').strip().lower()


def clean_username(value):
    """A valid Telegram username (5-32 chars of a-z, 0-9, _) or Refused('invalid_username')."""
    username = normalize_username(value) if isinstance(value, str) else ''
    if not USERNAME_PATTERN.match(username):
        raise Refused('invalid_username', 400)
    return username


def serialize(access):
    user = access.user
    return {
        'user_id': user.pk,
        'username': user.get_username(),
        'full_name': user.get_full_name().strip() or user.get_username(),
        'role': user.role,
        'telegram_username': access.telegram_username,
        'updated_at': access.updated_at.isoformat(),
    }


def list_access():
    return [serialize(access) for access in StaffTelegramAccess.objects.select_related('user').order_by('telegram_username')]


def _staff_user(user_id):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise Refused('not_found', 404)
    if user.role not in ALLOWED_ROLES:
        raise Refused('role_not_allowed', 400)
    return user


def get_access(user_id):
    user = _staff_user(user_id)
    access = StaffTelegramAccess.objects.select_related('user').filter(user=user).first()
    return serialize(access) if access else {
        'user_id': user.pk, 'username': user.get_username(), 'role': user.role, 'telegram_username': '',
    }


def set_access(user_id, raw_username, actor):
    user = _staff_user(user_id)
    username = clean_username(raw_username)
    try:
        with transaction.atomic():
            access, created = StaffTelegramAccess.objects.update_or_create(
                user=user, defaults={'telegram_username': username},
                create_defaults={'telegram_username': username, 'created_by': actor},
            )
    except IntegrityError:
        raise Refused('username_taken', 409)
    return serialize(StaffTelegramAccess.objects.select_related('user').get(pk=access.pk)), created


def clear_access(user_id):
    user = _staff_user(user_id)
    StaffTelegramAccess.objects.filter(user=user).delete()
