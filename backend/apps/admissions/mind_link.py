"""Naseeb Mind -> Naseeb Edu link: connect codes, signed requests and the attempt import.

A student presses "Bring my Naseeb Mind results"; ``start`` issues a one-time code (only its SHA-256
is stored, 10 minutes). Naseeb Mind then calls the signed ``complete`` endpoint with that code and
the student's finished attempts, and later ``sync`` with each new one. Every Mind request carries
``X-Naseeb-Timestamp`` and ``X-Naseeb-Signature`` = hex HMAC-SHA256(secret, "<timestamp>.<raw body>").

Imported attempts are ordinary ``ChallengeAttempt`` rows (source ``naseeb_mind``). Nothing here logs
answers or scores, and nothing existing is overwritten or deleted.
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .instrument_versions import INSTRUMENT_VERSION
from .models import ChallengeAttempt, MindLink, MindLinkCode

logger = logging.getLogger('apps.mind_link')

SIGNATURE_WINDOW_SECONDS = 300
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 200
MAX_BODY_BYTES = 2 * 1024 * 1024
LANGUAGES = ('uz', 'ru', 'en')
CODE_PATTERN = re.compile(r'^[0-9a-f]{32}$')
MAJOR_MAX = 160


class MindLinkError(Exception):
    def __init__(self, code, status):
        super().__init__(code)
        self.code = code
        self.status = status


def link_available():
    return bool(settings.MIND_LINK_SECRET)


def sign(secret, timestamp, body):
    """Hex HMAC-SHA256 of ``<timestamp>.<body>`` (the body as raw bytes)."""
    message = str(timestamp).encode() + b'.' + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_request(request):
    """Check a signed request and return its raw body. Raises MindLinkError (503, 413, 401)."""
    if not link_available():
        raise MindLinkError('link_off', 503)
    try:
        declared = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES:
        raise MindLinkError('payload_too_large', 413)
    body = request.body
    if len(body) > MAX_BODY_BYTES:
        raise MindLinkError('payload_too_large', 413)
    timestamp = request.META.get('HTTP_X_NAISEB_TIMESTAMP', '')
    given = request.META.get('HTTP_X_NAISEB_SIGNATURE', '')
    if not timestamp.isascii() or not timestamp.isdigit() or len(timestamp) > 12 or not given:
        raise MindLinkError('invalid_signature', 401)
    expected = sign(settings.MIND_LINK_SECRET, timestamp, body)
    valid = hmac.compare_digest(expected.encode(), given.strip().lower().encode('utf-8', 'ignore'))
    if not valid or abs(time.time() - int(timestamp)) > SIGNATURE_WINDOW_SECONDS:
        raise MindLinkError('invalid_signature', 401)
    return body


def parse_body(body):
    try:
        data = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise MindLinkError('invalid_payload', 400)
    if not isinstance(data, dict):
        raise MindLinkError('invalid_payload', 400)
    return data


def _invalid():
    return MindLinkError('invalid_payload', 400)


def _mind_user_id(data):
    value = data.get('mind_user_id')
    try:
        return uuid.UUID(value) if isinstance(value, str) else None
    except ValueError:
        pass
    raise _invalid()


def _chosen_major(data):
    value = data.get('chosen_major')
    if value is None:
        return ''
    if not isinstance(value, str) or len(value.strip()) > MAJOR_MAX:
        raise _invalid()
    return value.strip()


def _clean_attempts(data):
    raw = data.get('attempts')
    if not isinstance(raw, list):
        raise _invalid()
    if len(raw) > MAX_ATTEMPTS:
        raise MindLinkError('too_many_attempts', 400)
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            raise _invalid()
        external_id, challenge, version = item.get('id'), item.get('challenge'), item.get('instrument_version')
        if not all(isinstance(v, str) and v.strip() for v in (external_id, challenge, version)):
            raise _invalid()
        external_id, challenge, version = external_id.strip(), challenge.strip(), version.strip()
        if len(external_id) > 64 or len(challenge) > 40 or len(version) > 20:
            raise _invalid()
        answers, scores = item.get('answers'), item.get('scores', {})
        if not isinstance(answers, dict) or not isinstance(scores, dict):
            raise _invalid()
        completed = item.get('completed_at')
        parsed = None
        if isinstance(completed, str):
            try:
                parsed = parse_datetime(completed)
            except ValueError:
                parsed = None
        if parsed is None:
            raise _invalid()
        if timezone.is_naive(parsed):
            parsed = parsed.replace(tzinfo=dt_timezone.utc)
        cleaned.append({'id': external_id, 'challenge': challenge, 'version': version,
                        'answers': answers, 'scores': scores, 'completed_at': parsed})
    return cleaned


def import_attempts(student, attempts):
    """Store attempts not already stored. Returns (imported, skipped)."""
    imported = skipped = 0
    ids = [a['id'] for a in attempts]
    known = set(ChallengeAttempt.objects.filter(source=ChallengeAttempt.Source.MIND, external_id__in=ids)
                .values_list('external_id', flat=True))
    for attempt in attempts:
        expected = INSTRUMENT_VERSION.get(attempt['challenge'])
        if expected is None or attempt['id'] in known:
            skipped += 1
            continue
        try:
            # A savepoint per row: a clash on (student, challenge, completed_at) or a
            # concurrent import of the same id skips that row only.
            with transaction.atomic():
                ChallengeAttempt.objects.create(
                    student=student, challenge=attempt['challenge'], instrument_version=attempt['version'],
                    answers=attempt['answers'], scores=attempt['scores'], completed_at=attempt['completed_at'],
                    source=ChallengeAttempt.Source.MIND, external_id=attempt['id'],
                    source_version_mismatch=attempt['version'] != expected,
                )
        except IntegrityError:
            skipped += 1
            continue
        known.add(attempt['id'])
        imported += 1
    return imported, skipped


# --- student side ---------------------------------------------------------------------------

def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def status_for(student):
    link = MindLink.objects.filter(student=student).first()
    active = bool(link and link.active)
    payload = {
        'available': link_available(),
        'linked': active,
        'linked_at': link.linked_at if active else None,
        'last_sync_at': link.last_sync_at if active else None,
        'chosen_major': None,
    }
    # Offered only while the student has no major of their own; never applied silently.
    if link and link.chosen_major and not (student.target_major or '').strip():
        payload['chosen_major'] = link.chosen_major
    return payload


def start(student, lang=None):
    if not link_available():
        raise MindLinkError('link_off', 503)
    lang = lang if lang in LANGUAGES else 'uz'
    now = timezone.now()
    with transaction.atomic():
        link = MindLink.objects.select_for_update().filter(student=student).first()
        if link and link.active:
            raise MindLinkError('already_linked', 409)
        # A new code replaces every earlier one.
        MindLinkCode.objects.filter(student=student).delete()
        code = secrets.token_hex(16)
        expires_at = now + CODE_TTL
        MindLinkCode.objects.create(student=student, code_hash=_hash(code), expires_at=expires_at)
    return {'code': code, 'expires_at': expires_at,
            'url': f'{settings.MIND_SITE_URL}/connect?code={code}&lang={lang}'}


def unlink_student(student):
    now = timezone.now()
    MindLink.objects.filter(student=student, active=True).update(active=False, unlinked_at=now, updated_at=now)
    MindLinkCode.objects.filter(student=student).delete()
    return {'linked': False}


# --- Mind side (signed) ---------------------------------------------------------------------

def complete(data):
    code = data.get('code')
    if not isinstance(code, str) or not CODE_PATTERN.match(code):
        raise MindLinkError('code_invalid', 410)
    mind_user_id = _mind_user_id(data)
    if mind_user_id is None:
        raise _invalid()
    major = _chosen_major(data)
    attempts = _clean_attempts(data)
    now = timezone.now()
    with transaction.atomic():
        pending = (MindLinkCode.objects.select_for_update().select_related('student')
                   .filter(code_hash=_hash(code)).first())
        if pending is None or pending.used_at is not None or pending.expires_at <= now:
            raise MindLinkError('code_invalid', 410)
        student = pending.student
        # This student's own link first, then the Mind account's: both are locked.
        own = MindLink.objects.select_for_update().filter(student=student).first()
        theirs = MindLink.objects.select_for_update().filter(mind_user_id=mind_user_id).first()
        if own and own.active and own.mind_user_id != mind_user_id:
            raise MindLinkError('already_linked', 409)
        if theirs and theirs.active and theirs.student_id != student.id:
            raise MindLinkError('already_linked', 409)
        if theirs and theirs.student_id != student.id:
            # An old, inactive link of the same Mind account to someone else: it moves here.
            theirs.delete()
        if own and own.mind_user_id != mind_user_id:
            own.delete()
            own = None
        if own is None:
            own = MindLink(student=student, mind_user_id=mind_user_id)
        own.active, own.linked_at, own.unlinked_at, own.last_sync_at = True, now, None, now
        if major:
            own.chosen_major = major
        own.save()
        pending.used_at = now
        pending.save(update_fields=['used_at', 'updated_at'])
        imported, skipped = import_attempts(student, attempts)
    logger.info('mind-link complete: linked, imported=%s skipped=%s', imported, skipped)
    return {'linked': True, 'imported': imported, 'skipped': skipped}


def sync(data):
    mind_user_id = _mind_user_id(data)
    if mind_user_id is None:
        raise _invalid()
    major = _chosen_major(data)
    attempts = _clean_attempts(data)
    with transaction.atomic():
        link = (MindLink.objects.select_for_update().select_related('student')
                .filter(mind_user_id=mind_user_id, active=True).first())
        if link is None:
            raise MindLinkError('not_linked', 410)
        imported, skipped = import_attempts(link.student, attempts)
        link.last_sync_at = timezone.now()
        fields = ['last_sync_at', 'updated_at']
        if major and major != link.chosen_major:
            link.chosen_major = major
            fields.append('chosen_major')
        link.save(update_fields=fields)
    logger.info('mind-link sync: imported=%s skipped=%s', imported, skipped)
    return {'imported': imported, 'skipped': skipped}


def unlink_mind(data):
    mind_user_id = _mind_user_id(data)
    if mind_user_id is None:
        raise _invalid()
    now = timezone.now()
    MindLink.objects.filter(mind_user_id=mind_user_id, active=True).update(
        active=False, unlinked_at=now, updated_at=now)
    return {'unlinked': True}
