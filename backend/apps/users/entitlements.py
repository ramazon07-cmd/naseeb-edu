"""Plan entitlements: seat limits, feature flags and read-only workspaces.

Every seat-taking write (new account, reactivation, role change, school move)
goes through :func:`check` inside the caller's transaction. ``check`` locks the
workspace row first, so concurrent creations for the same school serialize on
that lock and the count they see already includes each other's inserts.
"""
from collections import namedtuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import PermissionDenied

from .localization import localized_message
from .models import PLAN_FEATURES, Plan, User, WorkspaceSubscription


SCHOOL_STANDARD = 'school-standard'
INDIVIDUAL_COUNSELOR = 'individual-counselor'
CENTER = 'center'

ALL_FEATURES = {key: True for key in PLAN_FEATURES}

# Defaults reproduce the behaviour before plans existed: three counselors per
# organization school, one owner per individual workspace, everything else
# unlimited. Real numbers are a pricing decision and are set per plan by staff.
DEFAULT_PLANS = {
    SCHOOL_STANDARD: {
        'name': 'School Standard',
        'description': 'Organization school workspace.',
        'max_counselors': 3,
        'max_students': None,
        'max_teachers': None,
        'features': ALL_FEATURES,
    },
    INDIVIDUAL_COUNSELOR: {
        'name': 'Individual Counselor',
        'description': 'Private workspace for one counselor.',
        'max_counselors': 1,
        'max_students': None,
        'max_teachers': 0,
        'features': {**ALL_FEATURES, 'organization_accounts': False},
    },
    CENTER: {
        'name': 'Center',
        'description': 'Education center or counseling agency with several counselors.',
        'max_counselors': None,
        'max_students': None,
        'max_teachers': None,
        'features': ALL_FEATURES,
    },
}

SEAT_ROLES = {
    'max_counselors': User.Role.COUNSELOR,
    'max_students': User.Role.STUDENT,
    'max_teachers': User.Role.TEACHER,
}
ROLE_SEATS = {role: key for key, role in SEAT_ROLES.items()}
SEAT_LABELS = {
    'max_counselors': 'active counselors',
    'max_students': 'active student accounts',
    'max_teachers': 'active teachers',
}

SeatState = namedtuple('SeatState', 'role school_id is_active')


class EntitlementError(ValidationError):
    """A plan limit or workspace state blocks the write."""

    def __init__(self, message, code):
        super().__init__({'school': [ValidationError(message, code=code)]})
        self.code = code
        self.detail_message = message

    def response_data(self):
        return {'detail': self.detail_message, 'code': self.code, 'school': [self.detail_message]}


def default_plan_code(workspace_type):
    from apps.admissions.models import School

    return INDIVIDUAL_COUNSELOR if workspace_type == School.WorkspaceType.INDIVIDUAL else SCHOOL_STANDARD


def default_plan(workspace_type):
    code = default_plan_code(workspace_type)
    plan, _ = Plan.objects.get_or_create(code=code, defaults=DEFAULT_PLANS[code])
    return plan


def ensure_subscription(school):
    subscription, _ = WorkspaceSubscription.objects.select_related('plan').get_or_create(
        school=school,
        defaults={'plan': lambda: default_plan(school.workspace_type)},
    )
    return subscription


def create_default_subscription(sender, instance, created, raw=False, **kwargs):
    """post_save receiver: every new workspace starts on its default plan."""
    if created and not raw:
        ensure_subscription(instance)


def seat_queryset(school_id, key):
    return User.objects.filter(school_id=school_id, role=SEAT_ROLES[key], is_active=True)


def check(school, key, delta=1, *, exclude_user_id=None):
    """Verify ``delta`` more ``key`` seats fit the workspace plan.

    Must run inside the caller's ``transaction.atomic()`` block so the lock is
    held until the new seat is written. Returns the locked School.
    """
    from apps.admissions.models import School

    if key not in SEAT_ROLES:
        raise KeyError(key)
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('entitlements.check() must run inside transaction.atomic().')
    locked = School.objects.select_for_update().get(pk=school.pk)
    subscription = WorkspaceSubscription.objects.select_related('plan').filter(school=locked).first()
    if subscription is None:
        subscription = ensure_subscription(locked)
    if delta <= 0:
        return locked
    if subscription.is_read_only:
        raise EntitlementError(
            'This workspace is read-only until its subscription is renewed.',
            'workspace_read_only',
        )
    limit = subscription.plan.limit(key)
    if limit is None:
        return locked
    used = seat_queryset(locked.pk, key)
    if exclude_user_id:
        used = used.exclude(pk=exclude_user_id)
    if used.count() + delta > limit:
        raise EntitlementError(
            f'This workspace plan allows at most {limit} {SEAT_LABELS[key]}.',
            'seat_limit_reached',
        )
    return locked


def seat_state(user):
    return SeatState(user.role, user.school_id, user.is_active)


def check_user_seat(user, *, previous=None):
    """Run :func:`check` when saving ``user`` takes a seat it did not hold.

    ``previous`` is the :class:`SeatState` before the change, or None for a new
    account. Edits that keep the same seat never re-check, so a workspace over
    its limit after a downgrade can still edit existing accounts.
    """
    key = ROLE_SEATS.get(user.role)
    if not key or not user.is_active or not user.school_id:
        return None
    if previous and previous == SeatState(user.role, user.school_id, True):
        return None
    return check(user.school, key, 1, exclude_user_id=user.pk)


def subscription_row(school_id):
    """(status, period_end, features) for one workspace in a single query."""
    return (
        WorkspaceSubscription.objects.filter(school_id=school_id)
        .values_list('status', 'period_end', 'plan__features')
        .first()
    )


def loaded_school_is_read_only(school):
    """Read-only state of a school fetched with ``select_related('subscription')``."""
    try:
        subscription = school.subscription
    except WorkspaceSubscription.DoesNotExist:
        return False
    return subscription.is_read_only


def feature_enabled(user, key):
    if key not in PLAN_FEATURES:
        raise KeyError(key)
    if user.is_product_admin:
        return True
    if user.role == User.Role.PARENT:
        return parent_feature_enabled(user, key)
    if not user.school_id:
        return True
    row = subscription_row(user.school_id)
    # Workspaces without a subscription predate plans and keep full access.
    return True if row is None else bool((row[2] or {}).get(key))


def parent_feature_enabled(user, key):
    """Parents have no school of their own: a feature is theirs when the plan
    of at least one linked child's school includes it (one query)."""
    from apps.admissions.models import ParentStudentLink

    school = 'student__school__subscription'
    return ParentStudentLink.objects.filter(
        Q(**{f'{school}__isnull': True}) | Q(**{f'{school}__plan__features__{key}': True}),
        parent=user, status=ParentStudentLink.Status.ACTIVE, student__school__isnull=False,
    ).exists()


def require_feature(request, key):
    if not feature_enabled(request.user, key):
        raise PermissionDenied({
            'detail': localized_message('feature_not_in_plan', request),
            'code': 'feature_not_in_plan',
        })


def require_school_feature(school, key):
    subscription = WorkspaceSubscription.objects.select_related('plan').filter(school=school).first()
    if subscription and not subscription.plan.has_feature(key):
        raise EntitlementError('This workspace plan does not include this feature.', 'feature_not_in_plan')


def workspace_summary(subscription):
    if subscription is None:
        return None
    plan = subscription.plan
    return {
        'plan': plan.code,
        'plan_name': plan.name,
        'status': subscription.status,
        'read_only': subscription.is_read_only,
        'period_start': subscription.period_start,
        'period_end': subscription.period_end,
        'limits': {key: plan.limit(key) for key in SEAT_ROLES},
        'features': dict(plan.features),
    }


def _seat_count(role):
    counts = (
        User.objects.filter(school=OuterRef('pk'), role=role, is_active=True)
        .order_by()
        .values('school')
        .annotate(total=Count('pk'))
        .values('total')
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), Value(0))


def annotate_seat_usage(queryset):
    """Seat usage per school as correlated counts: one query for any page size."""
    return queryset.annotate(**{
        f'{key}_used': _seat_count(role) for key, role in SEAT_ROLES.items()
    })
