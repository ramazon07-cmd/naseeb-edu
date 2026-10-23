"""An Essay Lab document can be the evidence for an assigned task.

Attaching explicitly shares it with the assigned counselor. Existing essay
access rules still decide who can read it and leave comments; task access alone
never reveals another student's private essay.
"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.users.audit import audit_product_action
from .essay_lab import access
from .models import Essay, Notification


def essay_submission_detail(task, user):
    essay = task.submission_essay
    if not essay or essay.student_id != task.student_id or essay.trashed_at is not None:
        return None
    caps = access.resolve_access(user, essay)
    if access.VIEW not in caps:
        return None
    return {
        'id': essay.pk, 'title': essay.title, 'word_count': essay.word_count,
        'shared_with_counselor': essay.shared_with_counselor, 'shared_at': essay.shared_at,
        'counselor_access': essay.counselor_access,
        'can_comment': access.COMMENT in caps,
        'is_owner': essay.student.user_id == user.pk,
    }


def prepare_essay_submission(task, essay_id, actor):
    """Called inside the task update's transaction, after locking the task."""
    essay = Essay.objects.select_for_update(of=('self',)).filter(
        pk=essay_id, student_id=task.student_id, student__user=actor, trashed_at__isnull=True,
    ).first()
    if not essay:
        raise ValidationError({'submission_essay': 'Choose one of your own available Essay Lab essays.'})
    if not essay.content.strip():
        raise ValidationError({'submission_essay': 'Write and save your essay before submitting it.'})
    counselor_id = task.student.assigned_counselor_id
    if not counselor_id:
        raise ValidationError({'submission_essay': 'A counselor must be assigned before you submit an essay for review.'})
    if not essay.shared_with_counselor:
        essay.shared_with_counselor = True
        essay.shared_at = timezone.now()
        essay.counselor_access = Essay.CounselorAccess.COMMENT
        essay.save(update_fields=['shared_with_counselor', 'shared_at', 'counselor_access'])
    audit_product_action(actor=actor, action='task.essay_submitted', target=task.student,
                         metadata={'task': task.pk, 'essay': essay.pk})
    Notification.objects.create(
        student=task.student, recipient_id=counselor_id, kind=Notification.Kind.TASK, target_id=task.pk,
        title='Essay submitted for a task',
        message='Your student attached an Essay Lab essay to an assigned task for your feedback.',
    )
    return essay
