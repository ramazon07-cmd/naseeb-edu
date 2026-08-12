import hashlib
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from .models import CredentialAuditEvent, TemporaryCredential, User


def generate_temporary_password(length=16):
    alphabet = string.ascii_letters + string.digits + '!@#$%&*'
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if any(char.islower() for char in password) and any(char.isupper() for char in password) and any(char.isdigit() for char in password):
            return password


def request_audit_metadata(request):
    if not request:
        return {}
    address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
    digest = hashlib.sha256(f'{settings.SECRET_KEY}:{address}'.encode()).hexdigest()[:20] if address else ''
    return {'ip_hash': digest, 'user_agent': request.META.get('HTTP_USER_AGENT', '')[:160]}


@transaction.atomic
def issue_temporary_credential(*, user, issued_by, raw_password=None, request=None, event=None):
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    password = raw_password or generate_temporary_password()
    validate_password(password, user=locked_user)
    now = timezone.now()
    had_previous = locked_user.temporary_credentials.exists()
    active = list(locked_user.temporary_credentials.select_for_update().filter(status=TemporaryCredential.Status.ISSUED))
    for credential in active:
        credential.status = TemporaryCredential.Status.REVOKED
        credential.revoked_at = now
        credential.save(update_fields=['status', 'revoked_at'])
        CredentialAuditEvent.objects.create(
            target_user=locked_user,
            actor=issued_by,
            event=CredentialAuditEvent.Event.REVOKED,
            credential=credential,
            metadata=request_audit_metadata(request),
        )

    locked_user.set_password(password)
    locked_user.must_change_password = True
    locked_user.password_version += 1
    locked_user.save(update_fields=['password', 'must_change_password', 'password_version'])
    credential = TemporaryCredential.objects.create(
        user=locked_user,
        issued_by=issued_by,
        expires_at=now + timedelta(hours=settings.TEMPORARY_CREDENTIAL_TTL_HOURS),
    )
    CredentialAuditEvent.objects.create(
        target_user=locked_user,
        actor=issued_by,
        event=event or (CredentialAuditEvent.Event.REISSUED if had_previous else CredentialAuditEvent.Event.ISSUED),
        credential=credential,
        metadata=request_audit_metadata(request),
    )
    return locked_user, credential, password, raw_password is None


def active_credential(user):
    return user.temporary_credentials.order_by('-issued_at', '-id').first()


@transaction.atomic
def mark_temporary_credential_used(*, user, request=None):
    credential = user.temporary_credentials.select_for_update().order_by('-issued_at', '-id').first()
    if not credential:
        return None, 'credential_missing'
    if credential.status == TemporaryCredential.Status.USED:
        return credential, 'credential_used'
    if credential.status != TemporaryCredential.Status.ISSUED:
        return credential, 'credential_missing'
    if credential.expires_at <= timezone.now():
        credential.status = TemporaryCredential.Status.EXPIRED
        credential.save(update_fields=['status'])
        CredentialAuditEvent.objects.create(
            target_user=user,
            event=CredentialAuditEvent.Event.EXPIRED,
            credential=credential,
            metadata=request_audit_metadata(request),
        )
        return credential, 'credential_expired'
    credential.status = TemporaryCredential.Status.USED
    credential.used_at = timezone.now()
    credential.save(update_fields=['status', 'used_at'])
    CredentialAuditEvent.objects.create(
        target_user=user,
        actor=user,
        event=CredentialAuditEvent.Event.USED,
        credential=credential,
        metadata=request_audit_metadata(request),
    )
    return credential, None


@transaction.atomic
def complete_password_change(*, user, new_password, request=None):
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    validate_password(new_password, user=locked_user)
    if locked_user.check_password(new_password):
        raise ValueError('password_reuse')
    locked_user.set_password(new_password)
    locked_user.must_change_password = False
    locked_user.password_version += 1
    locked_user.password_changed_at = timezone.now()
    locked_user.save(update_fields=['password', 'must_change_password', 'password_version', 'password_changed_at'])
    credential = locked_user.temporary_credentials.order_by('-issued_at', '-id').first()
    CredentialAuditEvent.objects.create(
        target_user=locked_user,
        actor=locked_user,
        event=CredentialAuditEvent.Event.PASSWORD_CHANGED,
        credential=credential,
        metadata=request_audit_metadata(request),
    )
    return locked_user
