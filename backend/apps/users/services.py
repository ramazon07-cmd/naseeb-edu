from django.core.exceptions import ValidationError
from django.db import transaction

from . import entitlements
from .audit import audit_product_action  # noqa: F401  (re-exported for existing callers)
from .models import User


def validate_counselor_capacity(*, school, exclude_user_id=None):
    """Lock the school row so concurrent API provisioning cannot exceed the plan."""
    return entitlements.check(school, 'max_counselors', 1, exclude_user_id=exclude_user_id)


@transaction.atomic
def transfer_counselor(*, counselor, school, actor):
    locked_school = validate_counselor_capacity(school=school, exclude_user_id=counselor.pk)
    previous_school = counselor.school
    counselor.school = locked_school
    counselor.is_active = True
    counselor.save(update_fields=['school', 'is_active'])
    if (
        previous_school
        and previous_school.workspace_type == previous_school.WorkspaceType.INDIVIDUAL
        and previous_school.owner_counselor_id == counselor.id
    ):
        previous_school.is_active = False
        previous_school.save(update_fields=['is_active', 'updated_at'])
    left = {}
    if previous_school and previous_school.pk != locked_school.pk:
        from apps.admissions.tenancy import user_left_school

        left = user_left_school(counselor, previous_school)
    audit_product_action(
        actor=actor,
        action='counselor.transferred',
        target=counselor,
        metadata={
            'from_school': previous_school.pk if previous_school else None,
            'to_school': locked_school.pk,
            **left,
        },
    )
    return counselor, previous_school


def validate_workspace_membership(*, role, school, user=None):
    """An individual workspace holds only its owner counselor and their students.

    Kept apart from the counselor-capacity rules on purpose: it depends only
    on the workspace type, not on plan limits.
    """
    from apps.admissions.models import School

    if school is None or school.workspace_type != School.WorkspaceType.INDIVIDUAL:
        return
    if role in {User.Role.ORGANIZATION, User.Role.TEACHER}:
        raise ValidationError({'school': 'An individual counselor workspace has no school or teacher accounts.'})
    if role == User.Role.COUNSELOR and (user is None or user.pk is None or school.owner_counselor_id != user.pk):
        raise ValidationError({'school': 'An individual counselor workspace belongs to its owner counselor only.'})
