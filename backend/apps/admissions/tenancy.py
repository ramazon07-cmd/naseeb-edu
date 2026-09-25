"""Moving people between schools.

Every path that changes which school a user belongs to goes through this
module, so the old school loses access in one place and in one transaction.
"""
import re
import secrets

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.users.models import User

from .models import ChannelMembership, MessageChannel, StudentProfile


def school_member_ids(school):
    """Users whose tenant is ``school`` (a student's tenant is their profile school)."""
    return User.objects.filter(
        (~Q(role__in=[User.Role.STUDENT, User.Role.PARENT]) & Q(school=school))
        | Q(role=User.Role.STUDENT, student_profile__school=school)
    ).values('pk')


@transaction.atomic
def user_left_school(user, old_school):
    """Cut every tie ``user`` kept with ``old_school``. Idempotent.

    * non-direct channel memberships in the old school are removed;
    * direct conversations held in the old school, or with anyone who still
      belongs to it, are archived (history stays, new messages are refused);
    * a counselor's assignments to students outside their current school are
      cleared, since an assignment never spans two schools.
    """
    summary = {'memberships_removed': 0, 'direct_channels_archived': 0, 'assignments_cleared': 0}
    if old_school is None:
        return summary
    summary['memberships_removed'], _ = ChannelMembership.objects.filter(
        user=user,
        channel__school=old_school,
    ).exclude(channel__kind=MessageChannel.Kind.DIRECT).delete()

    own_direct = ChannelMembership.objects.filter(
        user=user, channel__kind=MessageChannel.Kind.DIRECT,
    ).values('channel_id')
    shared_with_old_school = ChannelMembership.objects.filter(
        channel_id__in=own_direct,
        user_id__in=school_member_ids(old_school),
    ).exclude(user=user).values('channel_id')
    summary['direct_channels_archived'] = MessageChannel.objects.filter(
        Q(school=old_school) | Q(id__in=shared_with_old_school),
        id__in=own_direct,
        is_archived=False,
    ).exclude(direct_key__startswith='saved:').update(is_archived=True)

    if user.role == User.Role.COUNSELOR:
        stale = StudentProfile.objects.filter(assigned_counselor=user)
        if user.school_id:
            stale = stale.exclude(school_id=user.school_id)
        summary['assignments_cleared'] = stale.update(assigned_counselor=None, updated_at=timezone.now())
        if summary['assignments_cleared']:
            from .progress_cache import invalidate_progress_summary

            invalidate_progress_summary()
    return summary


def close_unreachable_direct_chats(user):
    """Archive ``user``'s direct chats with people who are no longer contacts.

    Used when a parent link ends: the link was the parent's only reach.
    """
    from .views.messaging import messaging_contacts_for

    own_direct = ChannelMembership.objects.filter(
        user=user, channel__kind=MessageChannel.Kind.DIRECT,
    ).values('channel_id')
    unreachable = ChannelMembership.objects.filter(channel_id__in=own_direct).exclude(user=user).exclude(
        user_id__in=messaging_contacts_for(user).values('pk'),
    ).values('channel_id')
    return MessageChannel.objects.filter(id__in=unreachable, is_archived=False).update(is_archived=True)


def _revoke_unused_credentials(user, actor):
    """A temporary password handed out by the old school must not outlive the move."""
    from apps.users.models import CredentialAuditEvent, TemporaryCredential

    now = timezone.now()
    revoked = list(user.temporary_credentials.select_for_update().filter(status=TemporaryCredential.Status.ISSUED))
    for credential in revoked:
        credential.status = TemporaryCredential.Status.REVOKED
        credential.revoked_at = now
        credential.save(update_fields=['status', 'revoked_at'])
        CredentialAuditEvent.objects.create(
            target_user=user,
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            event=CredentialAuditEvent.Event.REVOKED,
            credential=credential,
            metadata={'reason': 'school_changed'},
        )
    return len(revoked)


@transaction.atomic
def move_student(student, new_school, actor):
    """Move a student (profile or account) to ``new_school``. Idempotent.

    The account and the profile always change together. A counselor from
    another school is unassigned, the student leaves the old school's
    channels, unused temporary credentials issued there are revoked and the
    move is audited.
    """
    from django.core.exceptions import ValidationError

    from apps.users import entitlements
    from apps.users.services import audit_product_action

    from .models import School

    if new_school is None:
        raise ValidationError({'school': 'Students must belong to a school.'})
    profile_id = student.pk if isinstance(student, StudentProfile) else student.student_profile.pk
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    user = User.objects.select_for_update().get(pk=profile.user_id)
    school = School.objects.filter(pk=new_school.pk, is_active=True).first()
    if school is None:
        raise ValidationError({'school': 'Select an active school.'})
    if profile.school_id == school.pk and user.school_id == school.pk:
        return profile
    if user.is_active:
        # Holds the target school's row lock until the move is written.
        entitlements.check(school, 'max_students', 1, exclude_user_id=user.pk)

    old_school_id = profile.school_id if profile.school_id != school.pk else user.school_id
    old_school = School.objects.filter(pk=old_school_id).first() if old_school_id else None
    counselor_cleared = bool(
        profile.assigned_counselor_id
        and not User.objects.filter(pk=profile.assigned_counselor_id, school=school).exists()
    )
    if counselor_cleared:
        profile.assigned_counselor = None
    profile.school = school
    profile.school_name = school.name
    profile.save(update_fields=['school', 'school_name', 'assigned_counselor', 'updated_at'])
    user.school = school
    user.save(update_fields=['school'])

    summary = user_left_school(user, old_school)
    for parent in User.objects.filter(student_links__student=profile).distinct():
        close_unreachable_direct_chats(parent)
    revoked = _revoke_unused_credentials(user, actor)
    audit_product_action(
        actor=actor,
        action='student.moved',
        target=profile,
        metadata={
            'from_school': old_school.pk if old_school else None,
            'to_school': school.pk,
            'counselor_cleared': counselor_cleared,
            'credentials_revoked': revoked,
            **summary,
        },
    )
    # Keep the caller's instance in step with the rows just written.
    if isinstance(student, StudentProfile):
        student.refresh_from_db(fields=['school', 'school_name', 'assigned_counselor'])
        student.user.school = school
    else:
        student.school = school
    return profile


@transaction.atomic
def set_student_active(student, active, actor):
    """Deactivate or reactivate a student account. Idempotent; data is kept.

    Deactivation signs the student out everywhere, hides them from school
    staff and is audited.
    """
    from apps.users.services import audit_product_action

    from .models import ActivityLog

    profile_id = student.pk if isinstance(student, StudentProfile) else student.student_profile.pk
    profile = StudentProfile.objects.select_for_update().get(pk=profile_id)
    user = User.objects.select_for_update().get(pk=profile.user_id)
    if user.is_active == active and bool(profile.deactivated_at) != active:
        return profile
    if active and not user.is_active and user.school_id:
        from apps.users import entitlements

        # Reactivation takes a student seat again.
        entitlements.check(user.school, 'max_students', 1, exclude_user_id=user.pk)
    user.is_active = active
    profile.deactivated_at = None if active else timezone.now()
    update_fields = ['is_active']
    if not active:
        user.password_version += 1
        update_fields.append('password_version')
    user.save(update_fields=update_fields)
    profile.save(update_fields=['deactivated_at', 'updated_at'])
    action = 'student.reactivated' if active else 'student.deactivated'
    ActivityLog.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        student=profile,
        action=f"Student {'reactivated' if active else 'deactivated'}: {user.get_full_name() or user.username}",
    )
    audit_product_action(actor=actor, action=action, target=profile, metadata={'school': profile.school_id})
    if isinstance(student, StudentProfile):
        student.deactivated_at = profile.deactivated_at
        student.user.is_active = active
    else:
        student.is_active = active
    return profile


USERNAME_ATTEMPTS = 6


def _free_username(base):
    """The first free name in ``base``, ``base2``, ``base3``... in one query."""
    pattern = re.compile(rf'{re.escape(base)}(\d*)')
    taken = set()
    names = User.objects.filter(username__startswith=base, username__regex=rf'^{re.escape(base)}[0-9]*$')
    for name in names.values_list('username', flat=True):
        match = pattern.fullmatch(name)
        if match and not match.group(1).startswith('0'):
            taken.add(int(match.group(1) or 1))
    suffix = 1
    while suffix in taken:
        suffix += 1
    return base if suffix == 1 else f'{base}{suffix}'


@transaction.atomic
def create_student_account(*, school, full_name, password, created_by, email='', phone='', request=None):
    """The one way to create a student: account, profile and credential together.

    Every student therefore starts with a school, a profile in that school
    and an issued temporary credential. A taken email address is silently
    replaced with a placeholder so the result never reveals it. The username
    is the slugified name plus the lowest free number.
    """
    from django.conf import settings
    from django.db import IntegrityError
    from django.utils.text import slugify

    from apps.users import entitlements
    from apps.users.credentials import issue_temporary_credential

    from .models import ActivityLog
    from .services import ensure_student_profile

    parts = full_name.split()
    base_username = (slugify(full_name) or 'student')[:140]
    supplied_email = email if email and not User.objects.filter(email__iexact=email).exists() else ''
    username = _free_username(base_username)
    # Locks the school row until the account is written, so concurrent
    # creates cannot overshoot the plan's student seats.
    entitlements.check(school, 'max_students', 1)
    # The insert itself decides: a name taken by a concurrent create raises
    # IntegrityError and we look again, then fall back to a random suffix.
    for attempt in range(1, USERNAME_ATTEMPTS + 1):
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=supplied_email or f'{username}@{settings.PLACEHOLDER_EMAIL_DOMAIN}',
                    password=None,
                    first_name=parts[0],
                    last_name=' '.join(parts[1:]),
                    role=User.Role.STUDENT,
                    phone=phone,
                    school=school,
                )
            break
        except IntegrityError:
            if attempt == USERNAME_ATTEMPTS:
                raise
            if supplied_email and User.objects.filter(email__iexact=supplied_email).exists():
                supplied_email = ''  # lost a race for the address: same handling as above
            elif attempt < USERNAME_ATTEMPTS // 2:
                username = _free_username(base_username)
            else:
                username = f'{base_username}-{secrets.token_hex(3)}'
    user, _, _, _ = issue_temporary_credential(
        user=user, issued_by=created_by, raw_password=password, request=request,
    )
    profile = ensure_student_profile(
        user,
        assigned_counselor=created_by if created_by.role == User.Role.COUNSELOR else None,
    )
    ActivityLog.objects.create(actor=created_by, student=profile, action=f'Student profile created: {full_name}')
    return profile
