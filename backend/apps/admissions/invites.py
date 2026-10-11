"""Students joining by invite: personal invites, magic links and the pending queue.

* Tokens are ``secrets.token_urlsafe(32)``; only their SHA-256 is stored and the
  raw token is returned once, to the person who created the invite.
* An unknown, expired, revoked or used-up token, and an invite whose school or
  counselor is no longer active, all give the same ``invite_unavailable`` error.
* Accepting runs in one transaction: the invite row is locked, the request is
  validated against that locked row, and the use is claimed with a conditional
  UPDATE (so two accepts of a single-use invite can never both succeed, even
  without row locks).
* Joined students wait in ``awaiting_confirmation`` until their counselor
  confirms or rejects them; see scoping.student_lookups and authentication.py.
  They take no plan seat until confirmed (entitlements.seat_queryset): the seat
  limit is checked on confirmation, and a school holds at most
  ``MAX_PENDING_STUDENTS_PER_SCHOOL`` of them, so a leaked link cannot fill it.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import serializers

from apps.users import entitlements
from apps.users.audit import audit_product_action
from apps.users.localization import localized_message
from apps.users.models import User
from core.exceptions import CodedError

from .models import ActivityLog, StudentInvite, StudentProfile

TOKEN_BYTES = 32
MAX_TOKEN_LENGTH = 128
LINK_DEFAULT_HOURS = 24
LINK_MAX_HOURS = 7 * 24


def personal_invite_days():
    return getattr(settings, 'STUDENT_INVITE_TTL_DAYS', 7)


def hash_token(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def new_token():
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)


def join_path(raw):
    return f'/join/{raw}'


class InviteUnavailable(CodedError):
    status_code = 404

    def __init__(self, request=None):
        super().__init__(localized_message('invite_unavailable', request), 'invite_unavailable', 404)


def usable_invites(now=None):
    """Invites that can still admit a student, with an active school and counselor."""
    now = now or timezone.now()
    return StudentInvite.objects.filter(
        Q(max_uses__isnull=True) | Q(use_count__lt=F('max_uses')),
        revoked_at__isnull=True,
        expires_at__gt=now,
        school__is_active=True,
        counselor__is_active=True,
        counselor__role=User.Role.COUNSELOR,
        counselor__school_id=F('school_id'),
    )


def find_invite(raw, *, lock=False):
    """The usable invite for ``raw`` token, or None. Callers answer None generically."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_TOKEN_LENGTH:
        return None
    digest = hash_token(raw)
    queryset = usable_invites().select_related('school', 'counselor')
    if lock:
        queryset = queryset.select_for_update(of=('self',))
    return queryset.filter(token_hash=digest).first()


def invite_public_info(invite):
    """What the join page shows. A magic link reveals only the school and the counselor."""
    school = invite.school
    data = {
        'kind': invite.kind,
        'school': {'name': school.name, 'workspace_type': school.workspace_type},
        'counselor': {'name': invite.counselor.get_full_name() or invite.counselor.username},
        'expires_at': invite.expires_at,
    }
    if invite.kind == StudentInvite.Kind.PERSONAL:
        data['student'] = {
            'first_name': invite.first_name, 'last_name': invite.last_name,
            'email': invite.email, 'phone': invite.phone, 'grade': invite.grade,
        }
    return data


# -- Staff side -----------------------------------------------------------------

def invite_scope(user):
    """Invites ``user`` may list and revoke: a counselor's own, a school's for its
    organization account, every one for product admins."""
    queryset = StudentInvite.objects.select_related('counselor', 'school')
    if user.is_product_admin:
        return queryset
    if user.role == User.Role.COUNSELOR and user.school_id:
        return queryset.filter(counselor=user, school_id=user.school_id)
    if user.role == User.Role.ORGANIZATION and user.school_id:
        return queryset.filter(school_id=user.school_id)
    return queryset.none()


def pending_scope(user):
    """Pending students ``user`` may confirm or reject (same reach as the student scoping,
    without its "confirmed only" filter)."""
    queryset = StudentProfile.objects.filter(awaiting_confirmation=True, user__is_active=True)
    if user.is_product_admin:
        return queryset
    if user.role == User.Role.COUNSELOR and user.school_id:
        return queryset.filter(assigned_counselor=user, school_id=user.school_id, school__is_active=True)
    if user.role == User.Role.ORGANIZATION and user.school_id:
        return queryset.filter(school_id=user.school_id, school__is_active=True)
    return queryset.none()


def confirmed_in_scope(user, pk):
    """True when ``pk`` was pending for ``user`` but someone already confirmed it."""
    return _scope_without_pending(user).filter(pk=pk, awaiting_confirmation=False).exists()


def _scope_without_pending(user):
    queryset = StudentProfile.objects.filter(user__is_active=True)
    if user.is_product_admin:
        return queryset
    if user.role == User.Role.COUNSELOR and user.school_id:
        return queryset.filter(assigned_counselor=user, school_id=user.school_id)
    if user.role == User.Role.ORGANIZATION and user.school_id:
        return queryset.filter(school_id=user.school_id)
    return queryset.none()


def can_create_invites(user):
    return user.is_product_admin or user.role in {User.Role.COUNSELOR, User.Role.ORGANIZATION}


class InviteCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=StudentInvite.Kind.choices)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    grade = serializers.ChoiceField(choices=StudentProfile.Grade.choices, required=False, allow_blank=True)
    expires_in_hours = serializers.IntegerField(required=False, min_value=1, max_value=LINK_MAX_HOURS)
    # Organization accounts and product admins name the counselor; a counselor invites for themselves.
    counselor = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if attrs['kind'] == StudentInvite.Kind.PERSONAL:
            errors = {}
            for key in ('first_name', 'last_name', 'email'):
                if not attrs.get(key):
                    errors[key] = ['This field is required.']
            if errors:
                raise serializers.ValidationError(errors)
            attrs['email'] = attrs['email'].lower()
            if User.objects.filter(email__iexact=attrs['email']).exists():
                raise serializers.ValidationError({'email': ['This email address already has an account. Connect that student instead of inviting them.']})
        user = self.context['request'].user
        if user.role == User.Role.COUNSELOR and not user.is_product_admin:
            counselor = user
        else:
            if not attrs.get('counselor'):
                raise serializers.ValidationError({'counselor': ['Choose the counselor these students will work with.']})
            counselor = User.objects.filter(pk=attrs['counselor'], role=User.Role.COUNSELOR, is_active=True).select_related('school').first()
            if counselor is None or (not user.is_product_admin and counselor.school_id != user.school_id):
                raise serializers.ValidationError({'counselor': ['Choose an active counselor of this school.']})
        school = counselor.school
        if school is None or not school.is_active:
            raise serializers.ValidationError({'school': ['Your account is not connected to an active school.']})
        attrs['counselor_user'] = counselor
        attrs['school'] = school
        return attrs


@transaction.atomic
def create_invite(*, actor, data):
    """-> (invite, raw_token). A new personal invite replaces unused ones for the same email."""
    kind = data['kind']
    counselor = data['counselor_user']
    school = data['school']
    now = timezone.now()
    raw, digest = new_token()
    fields = {
        'kind': kind, 'token_hash': digest, 'school': school, 'counselor': counselor, 'created_by': actor,
    }
    if kind == StudentInvite.Kind.PERSONAL:
        StudentInvite.objects.filter(
            kind=kind, school=school, email__iexact=data['email'], revoked_at__isnull=True, use_count=0,
        ).update(revoked_at=now, updated_at=now)
        fields.update(
            email=data['email'], first_name=data['first_name'], last_name=data['last_name'],
            phone=data.get('phone', ''), grade=data.get('grade', ''),
            max_uses=1, expires_at=now + timedelta(days=personal_invite_days()),
        )
    else:
        hours = data.get('expires_in_hours') or LINK_DEFAULT_HOURS
        fields.update(max_uses=None, expires_at=now + timedelta(hours=hours))
    invite = StudentInvite.objects.create(**fields)
    audit_product_action(
        actor=actor, action='student_invite.created', target=invite,
        metadata={'kind': kind, 'counselor': counselor.pk, 'expires_at': invite.expires_at.isoformat()}, school=school,
    )
    return invite, raw


def revoke_invite(invite, actor):
    if invite.revoked_at:
        return invite
    invite.revoked_at = timezone.now()
    invite.save(update_fields=['revoked_at', 'updated_at'])
    audit_product_action(actor=actor, action='student_invite.revoked', target=invite, metadata={'kind': invite.kind}, school=invite.school)
    return invite


class InviteSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    counselor_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = StudentInvite
        fields = (
            'id', 'kind', 'status', 'email', 'first_name', 'last_name', 'phone', 'grade',
            'school', 'school_name', 'counselor', 'counselor_name',
            'created_at', 'expires_at', 'revoked_at', 'max_uses', 'use_count', 'last_used_at',
        )
        read_only_fields = fields

    def get_counselor_name(self, obj):
        return obj.counselor.get_full_name() or obj.counselor.username


class PendingStudentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    joined_at = serializers.DateTimeField(source='created_at', read_only=True)
    invite = serializers.SerializerMethodField()
    counselor_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = (
            'id', 'user_id', 'first_name', 'last_name', 'full_name', 'username', 'email', 'phone', 'grade',
            'school', 'joined_at', 'invite', 'counselor_name',
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_invite(self, obj):
        invite = obj.joined_invite
        if invite is None:
            return None
        return {'id': invite.pk, 'kind': invite.kind, 'created_at': invite.created_at, 'email': invite.email}

    def get_counselor_name(self, obj):
        counselor = obj.assigned_counselor
        return (counselor.get_full_name() or counselor.username) if counselor else None


@transaction.atomic
def confirm_student(profile, actor):
    """Make a pending student a normal one. This is when they take a plan seat:
    raises EntitlementError when the school is full or read-only."""
    locked = StudentProfile.objects.select_for_update().select_related('school', 'user').get(pk=profile.pk)
    if not locked.awaiting_confirmation:
        return locked
    entitlements.check(locked.school, 'max_students', 1, exclude_user_id=locked.user_id)
    locked.awaiting_confirmation = False
    locked.save(update_fields=['awaiting_confirmation', 'updated_at'])
    name = locked.user.get_full_name() or locked.user.username
    ActivityLog.objects.create(actor=actor, student=locked, action=f'Student confirmed: {name}')
    audit_product_action(actor=actor, action='student.join_confirmed', target=locked, metadata={'school': locked.school_id})
    return locked


@transaction.atomic
def reject_student(profile, actor):
    """Remove an unconfirmed account. It never reached any school data, so the
    account is deleted (freeing its email and username); should anything
    protect it, it is deactivated instead and can no longer sign in."""
    from .tenancy import set_student_active

    locked = StudentProfile.objects.select_for_update().select_related('user').get(pk=profile.pk)
    if not locked.awaiting_confirmation:
        return 'confirmed'
    user = locked.user
    audit_product_action(
        actor=actor, action='student.join_rejected', target=locked,
        metadata={'school': locked.school_id, 'invite': locked.joined_invite_id},
    )
    try:
        with transaction.atomic():
            user.delete()
        return 'deleted'
    except ProtectedError:
        set_student_active(locked, False, actor)
        return 'deactivated'


# -- Accepting ------------------------------------------------------------------

class AcceptSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, style={'input_type': 'password'})
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    grade = serializers.ChoiceField(choices=StudentProfile.Grade.choices, required=False, allow_blank=True)

    def validate_username(self, value):
        # Checked as it will be stored: NFKC folds look-alikes (full-width letters) together.
        value = User.normalize_username(value)
        try:
            UnicodeUsernameValidator()(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value

    def validate(self, attrs):
        invite = self.context['invite']
        personal = invite.kind == StudentInvite.Kind.PERSONAL
        if personal:
            # The counselor's details are the defaults; the student may correct their name.
            attrs['first_name'] = attrs.get('first_name') or invite.first_name
            attrs['last_name'] = attrs.get('last_name') or invite.last_name
            attrs['phone'] = attrs.get('phone') or invite.phone
            attrs['grade'] = attrs.get('grade') or invite.grade
            if (attrs.get('email') or '').lower() != invite.email.lower():
                raise serializers.ValidationError({'email': ['Use the email address this invitation was sent to.']})
            attrs['email'] = invite.email.lower()
        errors = {}
        for key in ('first_name', 'last_name', 'email'):
            if not attrs.get(key):
                errors[key] = ['This field is required.']
        if errors:
            raise serializers.ValidationError(errors)
        attrs['email'] = attrs['email'].lower()
        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': ['This email address is already used by another account.']})
        candidate = User(
            username=attrs['username'], email=attrs['email'],
            first_name=attrs['first_name'], last_name=attrs['last_name'], role=User.Role.STUDENT,
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)}) from exc
        return attrs


def max_pending_students():
    return getattr(settings, 'MAX_PENDING_STUDENTS_PER_SCHOOL', 100)


class InvitePaused(CodedError):
    """The school cannot take more joins right now (too many pending, or read-only)."""

    def __init__(self, request=None):
        super().__init__(localized_message('invite_paused', request), 'invite_paused', 400)


def _accepting(school):
    """Lock the school row; False when it may not take another pending student."""
    from apps.users.models import WorkspaceSubscription

    from .models import School

    locked = School.objects.select_for_update().get(pk=school.pk)
    subscription = WorkspaceSubscription.objects.filter(school=locked).first()
    if subscription is not None and subscription.is_read_only:
        return None
    pending = StudentProfile.objects.filter(school=locked, awaiting_confirmation=True, user__is_active=True).count()
    return locked if pending < max_pending_students() else None


def accept_invite(raw, payload, request=None):
    """Create the student's account from a usable invite. -> StudentProfile (pending).

    The invite is looked up once, locked, and the request validated against it.
    Raises InviteUnavailable, InvitePaused or serializers.ValidationError.
    """
    from .services import ensure_student_profile

    # Hashed before any lock is taken (the hasher is deliberately slow); only
    # something that could be a valid password is worth hashing.
    raw_password = payload.get('password') if hasattr(payload, 'get') else None
    password = make_password(raw_password) if isinstance(raw_password, str) and 0 < len(raw_password) <= 128 else None
    with transaction.atomic():
        invite = find_invite(raw, lock=True)
        if invite is None:
            raise InviteUnavailable(request)
        serializer = AcceptSerializer(data=payload, context={'invite': invite, 'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = _accepting(invite.school)
        if school is None:
            raise InvitePaused(request)
        now = timezone.now()
        # The claim itself is the guard: a single-use invite another accept used
        # after our read matches no row here.
        claimed = usable_invites(now).filter(pk=invite.pk).update(
            use_count=F('use_count') + 1, last_used_at=now, updated_at=now,
        )
        if claimed != 1:
            raise InviteUnavailable(request)
        try:
            with transaction.atomic():
                user = User.objects.create(
                    username=data['username'],
                    email=data['email'],
                    password=password,
                    first_name=data['first_name'],
                    last_name=data['last_name'],
                    phone=data.get('phone') or '',
                    role=User.Role.STUDENT,
                    school=school,
                    password_changed_at=now,
                )
        except IntegrityError:
            # Taken by a concurrent sign-up between validation and insert.
            raise serializers.ValidationError({'username': ['This username or email address is already in use.']}) from None
        profile = ensure_student_profile(user, assigned_counselor=invite.counselor)
        profile.awaiting_confirmation = True
        profile.joined_invite = invite
        # '' when not given, not the model's Grade 10 default: onboarding asks the student for it.
        profile.grade = data.get('grade') or ''
        profile.save(update_fields=['awaiting_confirmation', 'joined_invite', 'grade', 'updated_at'])
        audit_product_action(
            actor=user, action='student.joined_by_invite', target=profile,
            metadata={'invite': invite.pk, 'kind': invite.kind, 'counselor': invite.counselor_id}, school=school,
        )
    return profile, invite


def school_counselors(user):
    """Counselors an organization account (or a counselor: themselves) can invite for."""
    if user.role == User.Role.COUNSELOR and user.school_id:
        return User.objects.filter(pk=user.pk)
    if user.role == User.Role.ORGANIZATION and user.school_id:
        return User.objects.filter(school_id=user.school_id, role=User.Role.COUNSELOR, is_active=True).order_by('first_name', 'last_name', 'id')
    return User.objects.none()


def pending_join_info(user):
    """For /me: the school and counselor a pending student waits for, else None."""
    profile = getattr(user, 'student_profile', None) if user.role == User.Role.STUDENT else None
    if profile is None or not profile.awaiting_confirmation:
        return None
    counselor = profile.assigned_counselor
    school = profile.school if profile.school_id else None
    return {
        'school_name': school.name if school else '',
        'counselor_name': (counselor.get_full_name() or counselor.username) if counselor else '',
    }
