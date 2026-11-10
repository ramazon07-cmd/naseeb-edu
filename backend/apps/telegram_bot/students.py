"""Adding a student from the counselor bot.

The bot sends the name, email and phone a counselor typed; the account is made by
``create_student_account``, the same function the website's quick-create uses, so the
student gets the same school, profile, seat check and temporary password.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db.models import Q

from apps.admissions.models import StudentProfile
from apps.admissions.scoping import visible_students
from apps.admissions.tenancy import create_student_account
from apps.users import entitlements
from apps.users.audit import audit_product_action
from apps.users.cache_safety import count_hit
from apps.users.credentials import generate_temporary_password

from .services import Refused, User

# Same length as the website's quick-create.
PASSWORD_LENGTH = 10
NAME_LIMIT = 150
ADDS_PER_HOUR = 60
PHONE_DIGITS = re.compile(r'\d')


def normalize_phone(raw):
    """'+998 91 007 68 25', '91-007-68-25', '998910076825' -> '+998910076825'.

    Uzbek numbers get their country code; any other number with 9 to 15 digits is
    kept as '+digits'. Anything else is refused.
    """
    digits = ''.join(PHONE_DIGITS.findall(raw or ''))
    if len(digits) == 9:
        digits = '998' + digits
    if not 9 <= len(digits) <= 15:
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


def _existing(actor, email, phone):
    """A student of the actor's school with this email or phone, or ``None``."""
    digits = phone[1:]
    candidates = StudentProfile.objects.select_related('user').filter(
        school_id=actor.school_id, user__is_active=True, deactivated_at__isnull=True,
    ).filter(Q(user__email__iexact=email) | Q(user__phone__icontains=digits[-9:]))
    for profile in candidates[:20]:
        if profile.user.email.lower() == email:
            return profile
        if ''.join(PHONE_DIGITS.findall(profile.user.phone or ''))[-9:] == digits[-9:]:
            return profile
    return None


def _assign(profile, actor):
    """Make the new student visible in the bot to whoever added them."""
    if actor.role == User.Role.ASSISTANT:
        profile.assigned_counselor_id = actor.supervising_counselor_id
        profile.assigned_assistant = actor
        profile.save(update_fields=['assigned_counselor', 'assigned_assistant', 'updated_at'])


def add_student(link, *, full_name, email, phone):
    actor = link.user
    full_name, email, phone = clean_input(full_name, email, phone)
    school = actor.school
    if school is None or not school.is_active:
        raise Refused('account_unavailable')

    existing = _existing(actor, email, phone)
    if existing is not None:
        if visible_students(actor).filter(pk=existing.pk).exists():
            raise Refused(
                'student_exists', 409,
                full_name=existing.user.get_full_name().strip() or existing.user.username,
                username=existing.user.username,
            )
        raise Refused('student_exists_elsewhere', 409)

    hits = count_hit(f'tgbot-add-student:{link.chat_id}', 3600)
    if hits is not None and hits[0] > ADDS_PER_HOUR:
        raise Refused('too_many', 429)

    for attempt in range(3):
        password = generate_temporary_password(PASSWORD_LENGTH)
        try:
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
    _assign(profile, actor)
    student = profile.user
    credential = student.temporary_credentials.order_by('-issued_at', '-id').first()
    audit_product_action(
        actor=actor, action='student.created_via_bot', target=student, metadata={'school': school.id},
    )
    return {
        'full_name': student.get_full_name().strip() or student.username,
        # The login to hand out. Like quick-create, the answer never says whether the email was
        # already registered (that account then gets a placeholder), so the username is what always works.
        'username': student.username,
        'phone': phone,
        'temporary_password': password,
        'expires_at': credential.expires_at.isoformat() if credential else None,
        'login_url': f'{settings.FRONTEND_URL}/login',
    }
