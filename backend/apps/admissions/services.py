from django.db import transaction

from .models import StudentProfile, XPTransaction


TASK_XP_BY_PRIORITY = {
    'low': 25,
    'medium': 50,
    'high': 75,
    'urgent': 100,
}
ROADMAP_APPROVAL_XP = 75


@transaction.atomic
def award_approval_xp(*, student, source_type, source_id, amount, reason, awarded_by):
    """Award approval XP exactly once and return (transaction, was_created)."""
    locked_student = StudentProfile.objects.select_for_update().get(pk=student.pk)
    xp_transaction, created = XPTransaction.objects.get_or_create(
        source_type=source_type,
        source_id=source_id,
        defaults={
            'student': locked_student,
            'amount': amount,
            'reason': reason,
            'awarded_by': awarded_by,
        },
    )
    if created:
        locked_student.xp_total += amount
        locked_student.save(update_fields=['xp_total', 'updated_at'])
    return xp_transaction, created
