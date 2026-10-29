"""Counselor assistants: email invitations, accepting them, and splitting students.

* A counselor invites an assistant by email. Tokens follow the student-invite
  rules (invites.py): only the SHA-256 is stored, the raw token goes out once.
* Accepting creates a ``User.Role.ASSISTANT`` account in the counselor's school,
  supervised by that counselor. Single use, claimed with a conditional UPDATE.
* An assistant sees only students their counselor gave them, while those
  students stay with that counselor (scoping.student_lookups). Over those
  students they work as the counselor does (User.is_counselor_like); adding
  students, reassigning them and managing assistants stay with the counselor.
"""
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from apps.users.audit import audit_product_action
from apps.users.localization import localized_message
from apps.users.models import User

from .invites import MAX_TOKEN_LENGTH, AcceptSerializer, InviteUnavailable, hash_token, new_token
from .models import AssistantInvite, StudentProfile
from .progress_cache import invalidate_progress_summary
from .scoping import visible_students

logger = logging.getLogger(__name__)

CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'
MAX_ASSISTANT_STUDENTS = 500


def invite_days():
    return getattr(settings, 'ASSISTANT_INVITE_TTL_DAYS', 7)


def accept_path(raw):
    return f'/assistant-invite/{raw}'


def can_manage_assistants(user):
    return bool(
        user and user.is_authenticated and user.role == User.Role.COUNSELOR
        and user.school_id and user.school.is_active
    )


def usable_assistant_invites(now=None):
    now = now or timezone.now()
    return AssistantInvite.objects.filter(
        accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now,
        school__is_active=True, counselor__is_active=True, counselor__role=User.Role.COUNSELOR,
        counselor__school_id=F('school_id'),
    )


def find_assistant_invite(raw, *, lock=False):
    if not isinstance(raw, str) or not raw or len(raw) > MAX_TOKEN_LENGTH:
        return None
    queryset = usable_assistant_invites().select_related('school', 'counselor')
    if lock:
        queryset = queryset.select_for_update(of=('self',))
    return queryset.filter(token_hash=hash_token(raw)).first()


def assistant_invite_public_info(invite):
    return {
        'school': {'name': invite.school.name},
        'counselor': {'name': invite.counselor.get_full_name() or invite.counselor.username},
        'assistant': {'first_name': invite.first_name, 'last_name': invite.last_name, 'email': invite.email},
        'expires_at': invite.expires_at,
    }


# -- Counselor side ---------------------------------------------------------------

class AssistantInviteCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email address already has an account.')
        return value


@transaction.atomic
def create_assistant_invite(*, counselor, data):
    """-> (invite, raw_token). A new invite replaces this counselor's open ones for the same email."""
    now = timezone.now()
    usable_assistant_invites(now).filter(counselor=counselor, email__iexact=data['email']).update(
        revoked_at=now, updated_at=now,
    )
    raw, digest = new_token()
    invite = AssistantInvite.objects.create(
        token_hash=digest, school=counselor.school, counselor=counselor,
        email=data['email'], first_name=data['first_name'], last_name=data['last_name'],
        expires_at=now + timedelta(days=invite_days()),
    )
    audit_product_action(
        actor=counselor, action='assistant_invite.created', target=invite,
        metadata={'expires_at': invite.expires_at.isoformat()}, school=counselor.school,
    )
    return invite, raw


def send_assistant_invite_email(invite, raw, request=None):
    """True when the invitation went out by mail; False means the counselor shares the link.

    Mail failures never fail the invite: the link in the response still works.
    """
    console = settings.EMAIL_BACKEND == CONSOLE_BACKEND
    if console and not settings.DEBUG:
        # Printing the link would put a live token in production logs.
        return False
    counselor = invite.counselor.get_full_name() or invite.counselor.username
    values = {
        'name': invite.first_name, 'counselor': counselor, 'school': invite.school.name,
        'link': f'{settings.FRONTEND_URL}{accept_path(raw)}', 'days': invite_days(),
    }
    try:
        send_mail(
            localized_message('assistant_invite_subject', request).format(**values),
            localized_message('assistant_invite_body', request).format(**values),
            settings.DEFAULT_FROM_EMAIL,
            [invite.email],
        )
    except (SMTPException, OSError):
        logger.warning('Assistant invitation email failed for invite %s', invite.pk, exc_info=True)
        return False
    return not console


def revoke_assistant_invite(invite, actor):
    if invite.revoked_at or invite.accepted_at:
        return invite
    invite.revoked_at = timezone.now()
    invite.save(update_fields=['revoked_at', 'updated_at'])
    audit_product_action(actor=actor, action='assistant_invite.revoked', target=invite, school=invite.school)
    return invite


def assistants_of(counselor):
    return User.objects.filter(role=User.Role.ASSISTANT, supervising_counselor=counselor, school_id=counselor.school_id)


def assistant_student_ids(assistant):
    """The assistant's students as their counselor sees them (reassigned students drop out)."""
    return list(visible_students(assistant).values_list('pk', flat=True))


@transaction.atomic
def set_assistant_students(*, counselor, assistant, student_ids):
    """Give ``assistant`` exactly ``student_ids`` from the counselor's own students.

    Raises ValidationError for an id the counselor cannot see. Returns the new id list.
    """
    ids = set(student_ids)
    own = visible_students(counselor)
    found = set(own.filter(pk__in=ids).values_list('pk', flat=True))
    if found != ids:
        raise serializers.ValidationError({'students': ['Choose only your own active students.']})
    now = timezone.now()
    removed = own.filter(assigned_assistant=assistant).exclude(pk__in=ids).update(assigned_assistant=None, updated_at=now)
    added = own.filter(pk__in=ids).exclude(assigned_assistant=assistant).update(assigned_assistant=assistant, updated_at=now)
    if removed or added:
        invalidate_progress_summary()
        audit_product_action(
            actor=counselor, action='assistant.students_set', target=assistant,
            metadata={'students': sorted(ids), 'added': added, 'removed': removed}, school=counselor.school,
        )
    return sorted(ids)


@transaction.atomic
def deactivate_assistant(*, counselor, assistant):
    """The assistant can no longer sign in; their students go back to the counselor alone."""
    StudentProfile.objects.filter(assigned_assistant=assistant).update(assigned_assistant=None, updated_at=timezone.now())
    if assistant.is_active:
        assistant.is_active = False
        # Bumping the version revokes the assistant's open sessions (VersionedJWTAuthentication).
        assistant.password_version += 1
        assistant.save(update_fields=['is_active', 'password_version'])
        audit_product_action(actor=counselor, action='account.deactivated', target=assistant, school=counselor.school)
    invalidate_progress_summary()
    return assistant


# -- Accepting --------------------------------------------------------------------

class AssistantAcceptSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, style={'input_type': 'password'})

    # Same username rules as student sign-up (NFKC-normalized, unique case-insensitively).
    validate_username = AcceptSerializer.validate_username

    def validate(self, attrs):
        invite = self.context['invite']
        candidate = User(
            username=attrs['username'], email=invite.email,
            first_name=invite.first_name, last_name=invite.last_name, role=User.Role.ASSISTANT,
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)}) from exc
        return attrs


def accept_assistant_invite(raw, payload, request=None):
    """Create the assistant's account from a usable invite. -> (user, invite).

    Raises InviteUnavailable or serializers.ValidationError.
    """
    # Hashed before the lock (the hasher is deliberately slow).
    raw_password = payload.get('password') if hasattr(payload, 'get') else None
    password = make_password(raw_password) if isinstance(raw_password, str) and 0 < len(raw_password) <= 128 else None
    with transaction.atomic():
        invite = find_assistant_invite(raw, lock=True)
        if invite is None:
            raise InviteUnavailable(request)
        serializer = AssistantAcceptSerializer(data=payload, context={'invite': invite})
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        # The claim is the guard: a second accept of the same link matches no row.
        claimed = usable_assistant_invites(now).filter(pk=invite.pk).update(accepted_at=now, updated_at=now)
        if claimed != 1:
            raise InviteUnavailable(request)
        if User.objects.filter(email__iexact=invite.email).exists():
            raise serializers.ValidationError({'email': ['This email address is already used by another account.']})
        try:
            with transaction.atomic():
                user = User.objects.create(
                    username=serializer.validated_data['username'], email=invite.email, password=password,
                    first_name=invite.first_name, last_name=invite.last_name,
                    role=User.Role.ASSISTANT, school=invite.school, supervising_counselor=invite.counselor,
                    password_changed_at=now,
                )
        except IntegrityError:
            raise serializers.ValidationError({'username': ['This username or email address is already in use.']}) from None
        AssistantInvite.objects.filter(pk=invite.pk).update(accepted_user=user)
        audit_product_action(
            actor=user, action='assistant.joined_by_invite', target=user,
            metadata={'invite': invite.pk, 'counselor': invite.counselor_id}, school=invite.school,
        )
    return user, invite
