from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ProductAuditEvent, User


ORGANIZATION_SCHOOL_COUNSELOR_LIMIT = 3


def audit_product_action(*, actor, action, target, metadata=None):
    return ProductAuditEvent.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        target_type=target._meta.label_lower,
        target_id=str(target.pk or ''),
        target_label=str(target),
        metadata=metadata or {},
    )


def validate_counselor_capacity(*, school, exclude_user_id=None):
    """Lock the school row so concurrent API provisioning cannot exceed the limit."""
    from apps.admissions.models import School

    locked_school = School.objects.select_for_update().get(pk=school.pk)
    if locked_school.workspace_type == School.WorkspaceType.INDIVIDUAL:
        return locked_school
    active = User.objects.filter(
        school=locked_school,
        role=User.Role.COUNSELOR,
        is_active=True,
    )
    if exclude_user_id:
        active = active.exclude(pk=exclude_user_id)
    if active.count() >= ORGANIZATION_SCHOOL_COUNSELOR_LIMIT:
        raise ValidationError({
            'school': f'An organization school can have at most {ORGANIZATION_SCHOOL_COUNSELOR_LIMIT} active counselors.'
        })
    return locked_school


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
    audit_product_action(
        actor=actor,
        action='counselor.transferred',
        target=counselor,
        metadata={'from_school': previous_school.pk if previous_school else None, 'to_school': locked_school.pk},
    )
    return counselor, previous_school
