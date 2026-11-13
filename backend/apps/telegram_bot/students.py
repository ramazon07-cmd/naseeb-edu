"""Adding a student, and giving a student a new temporary password, from the counselor bot.

The bot sends the name, email and phone a counselor typed; the account is made by
``create_student_account``, the same function the website's quick-create uses, so the
student gets the same school, profile, seat check and temporary password. A new password
goes through ``issue_temporary_credential``, as on the website's account page, and only
for a student the bot already lists for that counselor or assistant.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.admissions.models import School
from apps.admissions.scoping import active_visible_students, visible_students
from apps.admissions.tenancy import create_student_account, find_school_student
from apps.users import entitlements
from apps.users.audit import audit_product_action
from apps.users.cache_safety import count_hit
from apps.users.credentials import generate_temporary_password, issue_temporary_credential
from apps.users.models import TemporaryCredential

from .services import Refused, User

# Same length as the website's quick-create.
PASSWORD_LENGTH = 10
NAME_LIMIT = 150
ADDS_PER_HOUR = 60
RESETS_PER_HOUR = 30
SEARCH_RESULTS = 8
QUERY_LIMIT = 100
PHONE_DIGITS = re.compile(r'\d')
# A repeat of an add the same person made this recently (the bot timed out and they tapped
# again) gets a fresh password for that student instead of "already exists".
RETRY_WINDOW = timedelta(minutes=30)


def normalize_phone(raw):
    """'+998 91 007 68 25', '91-007-68-25', '8 91 007 68 25', '998910076825' -> '+998910076825'.

    Uzbek numbers get their country code (an old 8 or 0 trunk prefix is dropped); any
    other number with 11 to 15 digits is kept as '+digits'. Anything else is refused.
    """
    digits = ''.join(PHONE_DIGITS.findall(raw or ''))
    if len(digits) == 10 and digits[0] in '80':
        digits = digits[1:]
    if len(digits) == 9:
        digits = '998' + digits
    if not 11 <= len(digits) <= 15:
        raise Refused('invalid_phone', 400)
    return '+' + digits


def clean_input(full_name, email, phone):
    full_name = ' '.join(str(full_name or '').split())
    if not full_name or len(full_name) > NAME_LIMIT:
        raise Refused('invalid_name', 400)
    email = str(email or '').strip().lstrip('@').lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        raise Refused('invalid_email', 400)
    return full_name, email, normalize_phone(phone)


def _assign(profile, actor):
    """Make the new student visible in the bot to whoever added them."""
    if actor.role == User.Role.ASSISTANT:
        profile.assigned_counselor_id = actor.supervising_counselor_id
        profile.assigned_assistant = actor
        profile.save(update_fields=['assigned_counselor', 'assigned_assistant', 'updated_at'])


def _just_added_by(student, actor):
    """True when `actor` added `student` minutes ago and the student has not signed in yet."""
    credential = student.temporary_credentials.order_by('-issued_at', '-id').first()
    return bool(
        credential and credential.issued_by_id == actor.pk
        and credential.status == TemporaryCredential.Status.ISSUED
        and credential.issued_at >= timezone.now() - RETRY_WINDOW
    )


def _name(user):
    return user.get_full_name().strip() or user.username


def _payload(student, password, phone=None):
    credential = student.temporary_credentials.order_by('-issued_at', '-id').first()
    payload = {
        'full_name': _name(student),
        # The login to hand out. Like quick-create, the answer never says whether the email was
        # already registered (that account then gets a placeholder), so the username is what always works.
        'username': student.username,
        'temporary_password': password,
        'expires_at': credential.expires_at.isoformat() if credential else None,
        'login_url': f'{settings.FRONTEND_URL}/login',
    }
    if phone is not None:
        payload['phone'] = phone
    return payload


def add_student(link, *, full_name, email, phone):
    actor = link.user
    full_name, email, phone = clean_input(full_name, email, phone)
    if actor.school_id is None:
        raise Refused('account_unavailable')

    with transaction.atomic():
        # One add per school at a time, so two quick taps cannot both pass the duplicate check.
        school = School.objects.select_for_update().get(pk=actor.school_id)
        if not school.is_active:
            raise Refused('account_unavailable')
        existing = find_school_student(school, email, phone, full_name)
        if existing is not None:
            if not visible_students(actor).filter(pk=existing.pk).exists():
                raise Refused('student_exists_elsewhere', 409)
            if _just_added_by(existing.user, actor):
                # The first answer never reached the bot: hand out a fresh password for the same account.
                password = generate_temporary_password(PASSWORD_LENGTH)
                student, _, _, _ = issue_temporary_credential(
                    user=existing.user, issued_by=actor, raw_password=password,
                )
                return _payload(student, password, phone)
            raise Refused(
                'student_exists', 409,
                full_name=_name(existing.user),
                username=existing.user.username,
            )

        hits = count_hit(f'tgbot-add-student:{link.chat_id}', 3600)
        if hits is not None and hits[0] > ADDS_PER_HOUR:
            raise Refused('too_many', 429)

        for attempt in range(3):
            password = generate_temporary_password(PASSWORD_LENGTH)
            try:
                with transaction.atomic():
                    profile = create_student_account(
                        school=school, full_name=full_name, password=password, created_by=actor,
                        email=email, phone=phone,
                    )
                break
            except entitlements.EntitlementError:
                raise Refused('seat_limit', 403)
            except DjangoValidationError:
                # The random password was too close to the name; nothing was saved, so try another.
                if attempt == 2:
                    raise
        # In the same transaction as the account: a failure here leaves no student whose password nobody saw.
        _assign(profile, actor)
        audit_product_action(
            actor=actor, action='student.created_via_bot', target=profile.user, metadata={'school': school.id},
        )
        return _payload(profile.user, password, phone)


def find_students(link, query):
    """The caller's active students whose name, login or email holds every word of ``query``."""
    words = ' '.join(str(query or '').split())
    if len(words) < 2 or len(words) > QUERY_LIMIT:
        raise Refused('invalid_query', 400)
    match = Q()
    for word in words.split():
        match &= (
            Q(user__first_name__icontains=word) | Q(user__last_name__icontains=word)
            | Q(user__username__icontains=word) | Q(user__email__icontains=word)
        )
    rows = list(
        active_visible_students(link.user).filter(match).select_related('user')
        .order_by('user__first_name', 'user__last_name', 'id')[:SEARCH_RESULTS + 1]
    )
    return {
        'students': [
            {'id': profile.pk, 'full_name': _name(profile.user), 'username': profile.user.username}
            for profile in rows[:SEARCH_RESULTS]
        ],
        'more': len(rows) > SEARCH_RESULTS,
    }


def reset_password(link, student_id):
    """A new temporary password for one of the caller's students; the old one stops working."""
    actor = link.user
    if isinstance(student_id, bool) or not isinstance(student_id, int):
        raise Refused('invalid_request', 400)
    profile = active_visible_students(actor).select_related('user').filter(pk=student_id).first()
    if profile is None:
        # Not theirs, deactivated or gone: the same answer, so ids of other schools tell nothing.
        raise Refused('student_not_found', 404)
    hits = count_hit(f'tgbot-reset-password:{link.chat_id}', 3600)
    if hits is not None and hits[0] > RESETS_PER_HOUR:
        raise Refused('too_many', 429)
    with transaction.atomic():
        for attempt in range(3):
            password = generate_temporary_password(PASSWORD_LENGTH)
            try:
                with transaction.atomic():
                    student, _, _, _ = issue_temporary_credential(
                        user=profile.user, issued_by=actor, raw_password=password,
                    )
                break
            except DjangoValidationError:
                # The random password was too close to the name; nothing was saved, so try another.
                if attempt == 2:
                    raise
        audit_product_action(
            actor=actor, action='credential.issued', target=student, metadata={'role': student.role, 'via': 'bot'},
        )
    return _payload(student, password)
