"""Who may do what with one essay: `resolve_access(user, essay)`.

The owner student can do everything. Anyone else needs the essay shared
(and not in the trash): the student's assigned counselor, in the student's
own active school, gets what `Essay.counselor_access` allows; a platform
admin may only read (their reads are audited). Everyone else — other
counselors, school accounts, teachers, parents — gets nothing, so the essay
and its comments look missing to them.
"""

from apps.users.models import User

VIEW = 'view'
COMMENT = 'comment'
SUGGEST = 'suggest'
EDIT = 'edit'
# Only the owner accepts or rejects suggestions and edits the text directly.
DECIDE = 'decide'

NONE = frozenset()
OWNER = frozenset({VIEW, COMMENT, SUGGEST, EDIT, DECIDE})
READ_ONLY = frozenset({VIEW})
BY_COUNSELOR_ACCESS = {
    'comment': frozenset({VIEW, COMMENT}),
    'suggest': frozenset({VIEW, COMMENT, SUGGEST}),
    'edit': frozenset({VIEW, COMMENT, SUGGEST, EDIT}),
}


def resolve_access(user, essay):
    """The capabilities `user` has on `essay` (its `student`, `student.user` and `student.school` are read)."""
    if not user or not user.is_authenticated or not user.is_active:
        return NONE
    student = essay.student
    if user.role == User.Role.STUDENT and not user.is_product_admin:
        return OWNER if student.user_id == user.id else NONE
    if not essay.shared_with_counselor or essay.trashed_at is not None:
        return NONE
    if user.is_product_admin:
        return READ_ONLY
    if user.role != User.Role.COUNSELOR:
        return NONE
    if not (
        user.school_id
        and student.assigned_counselor_id == user.id
        and student.school_id == user.school_id
        and student.school is not None and student.school.is_active
        and student.user.is_active
        and student.deactivated_at is None
    ):
        return NONE
    return BY_COUNSELOR_ACCESS.get(essay.counselor_access, BY_COUNSELOR_ACCESS['comment'])
