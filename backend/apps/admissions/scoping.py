"""One definition of "which students can this user see".

Canonical rule:
* product admin (superuser or ADMIN role): every student;
* counselor: students assigned to them *in their own school*;
* teacher / organization: students of their school;
* student: their own profile;
* anyone else, or staff without a school: nobody;
* staff of a deactivated school: nobody;
* deactivated students are visible to product admins only;
* essays additionally need to be shared by their student to be seen by anyone else.

Views may still restrict roles further (e.g. teachers cannot list tasks);
they should never widen this scope.
"""
from apps.users.models import User

from .models import StudentProfile

_NOBODY = False


def tenant_school(user):
    """The school ``user`` acts within, or ``None``.

    A student's school is their profile's school. Parents never belong to a
    school: their reach comes only from accepted links to their children.
    """
    if not user or not user.is_authenticated or user.role == User.Role.PARENT:
        return None
    if user.role == User.Role.STUDENT:
        profile = getattr(user, 'student_profile', None)
        if profile is not None and profile.school_id:
            return profile.school
    return user.school if user.school_id else None


def tenant_school_id(user):
    if not user or not user.is_authenticated or user.role == User.Role.PARENT:
        return None
    if user.role == User.Role.STUDENT:
        profile = getattr(user, 'student_profile', None)
        if profile is not None and profile.school_id:
            return profile.school_id
    return user.school_id


def is_locked_out_by_school(user):
    """True when the user's school was deactivated (product admins are exempt)."""
    if not user or not user.is_authenticated or user.is_product_admin:
        return False
    school = tenant_school(user)
    return school is not None and not school.is_active


def student_lookups(user):
    """Return ORM lookups relative to StudentProfile, ``None`` for all, ``False`` for nobody."""
    if not user or not user.is_authenticated:
        return _NOBODY
    if user.is_product_admin:
        return None
    if user.role == User.Role.COUNSELOR:
        if not user.school_id:
            return _NOBODY
        return {
            'assigned_counselor': user, 'school_id': user.school_id,
            'school__is_active': True, 'user__is_active': True,
        }
    if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
        if not user.school_id:
            return _NOBODY
        return {'school_id': user.school_id, 'school__is_active': True, 'user__is_active': True}
    if user.role == User.Role.STUDENT:
        return {'user': user}
    return _NOBODY


def student_scope_key(user):
    """A string naming ``user``'s student scope, equal for users who see the
    same students (e.g. teachers of one school); ``None`` when they see nobody."""
    lookups = student_lookups(user)
    if lookups is None:
        return 'all'
    if lookups is _NOBODY:
        return None
    return ';'.join(f'{key}={getattr(value, "pk", value)}' for key, value in sorted(lookups.items()))


def scope_students(queryset, user, *, via=None):
    """Filter ``queryset`` to rows whose student is visible to ``user``.

    ``via`` is the path from the queryset's model to StudentProfile
    (``None`` when the queryset is StudentProfile itself, ``'student'`` for
    most records).
    """
    lookups = student_lookups(user)
    if lookups is None:
        return queryset
    if lookups is _NOBODY:
        return queryset.none()
    prefix = f'{via}__' if via else ''
    return queryset.filter(**{f'{prefix}{key}': value for key, value in lookups.items()})


def owns_essays_only(user):
    """True for a student reading their own essays: they see every document."""
    return bool(
        user and user.is_authenticated and user.role == User.Role.STUDENT and not user.is_product_admin
    )


def shared_essay_lookups(user):
    """Lookups hiding the essays a student has not shared, unless ``user`` is that student.

    Essays are private by default: anyone other than the owner (counselor,
    school staff, product admins, parents) sees only shared ones.
    """
    return {} if owns_essays_only(user) else {'shared_with_counselor': True}


def scope_essays(queryset, user):
    """Essays ``user`` may read: scoped by student, then by sharing."""
    return scope_students(queryset, user, via='student').filter(**shared_essay_lookups(user))


def visible_students(user, queryset=None):
    if queryset is None:
        queryset = StudentProfile.objects.all()
    return scope_students(queryset, user)


def active_visible_students(user, queryset=None):
    """Visible students who count in totals: deactivated ones are left out."""
    return visible_students(user, queryset).filter(user__is_active=True, deactivated_at__isnull=True)


SCHOOL_STAFF_ROLES = (User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION)


def school_staff(school_id, roles=SCHOOL_STAFF_ROLES):
    """Active staff accounts of one school (none without a school)."""
    if not school_id:
        return User.objects.none()
    return User.objects.filter(school_id=school_id, role__in=roles, is_active=True)


def booking_participants_for(profile):
    """Staff of the student's current school (their assigned counselor included)."""
    school_id = profile.school_id if profile else None
    return school_staff(school_id).order_by('role', 'first_name', 'last_name', 'username')
