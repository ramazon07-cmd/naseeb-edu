from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ActivityLog, Document, Notification, RoadmapMission, StudentProfile, Task, XPTransaction
from .progress import OPEN_MISSION_STATUSES, OPEN_TASK_STATUSES


TASK_XP_BY_PRIORITY = {
    'low': 25,
    'medium': 50,
    'high': 75,
    'urgent': 100,
}
ROADMAP_APPROVAL_XP = 75
LEVEL_ONE_MISSIONS = (
    {
        'sequence': 1,
        'title': 'Complete your student profile baseline',
        'category': 'Profile',
        'description': 'Confirm your academics, goals, target countries and scholarship preferences.',
    },
    {
        'sequence': 2,
        'title': 'Map your strengths and application goals',
        'category': 'Strategy',
        'description': 'Identify your strongest academic and extracurricular themes for the application.',
    },
    {
        'sequence': 3,
        'title': 'Build a balanced university shortlist',
        'category': 'Applications',
        'description': 'Compare reach, target and safety options with scholarship deadlines.',
    },
    {
        'sequence': 4,
        'title': 'Create your activities and honors inventory',
        'category': 'Activities',
        'description': 'Collect the impact, dates and evidence for your main activities and honors.',
    },
    {
        'sequence': 5,
        'title': 'Prepare your testing and academic plan',
        'category': 'Academics',
        'description': 'Set the next SAT, IELTS and transcript milestones with realistic deadlines.',
    },
    {
        'sequence': 6,
        'title': 'Plan recommendation letter requests',
        'category': 'Recommendations',
        'description': 'Choose recommenders and prepare the information they need to write strong letters.',
    },
    {
        'sequence': 7,
        'title': 'Complete personal statement package',
        'category': 'Essays',
        'description': 'Finish the main essay and prepare the first supplement outline.',
    },
    {
        'sequence': 8,
        'title': 'Complete the Level 1 readiness review',
        'category': 'Review',
        'description': 'Review your Level 1 work with staff and record the next application priorities.',
    },
)


@transaction.atomic
def extend_level_one_roadmap(*, student, assigned_by, start_date=None):
    """Create or align the standard Level 1 path without resetting existing work."""
    start_date = start_date or timezone.localdate()
    missions = []
    created_count = 0
    previous = None

    for item in LEVEL_ONE_MISSIONS:
        defaults = {
            'assigned_by': assigned_by,
            'category': item['category'],
            'description': item['description'],
            'level': 1,
            'sequence': item['sequence'],
            'prerequisite': previous,
            'due_date': start_date + timedelta(days=item['sequence'] * 7),
            'status': RoadmapMission.Status.PLANNED,
        }
        mission, created = RoadmapMission.objects.get_or_create(
            student=student,
            title=item['title'],
            defaults=defaults,
        )
        created_count += int(created)

        update_fields = []
        for field, value in {
            'level': 1,
            'sequence': item['sequence'],
            'prerequisite': previous,
        }.items():
            current_value = (
                getattr(mission, 'prerequisite_id')
                if field == 'prerequisite'
                else getattr(mission, field)
            )
            target_value = getattr(value, 'id', None) if field == 'prerequisite' else value
            if current_value != target_value:
                setattr(mission, field, value)
                update_fields.append(field)
        if not mission.assigned_by_id:
            mission.assigned_by = assigned_by
            update_fields.append('assigned_by')
        if update_fields:
            mission.save(update_fields=[*update_fields, 'updated_at'])

        missions.append(mission)
        previous = mission

    return missions, created_count


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


SEND_BACK_NOTICE_TITLE = 'Your counselor asked for changes'
APPROVAL_NOTICE_TITLE = 'Your counselor approved your work'
NOTE_LIMIT = 2000


def record_send_back(*, record, student, note, actor, notice_kind, label):
    """Tell a student what to change on a record a counselor sent back.

    The status change (if any) is the caller's; this writes the student's
    notice and the timeline entry, so every kind of send-back reads the same.
    """
    Notification.objects.create(
        student=student,
        title=SEND_BACK_NOTICE_TITLE,
        message=f'{record.title}: {note}',
        kind=notice_kind,
        target_id=record.pk,
    )
    ActivityLog.objects.create(
        actor=actor,
        student=student,
        action=f'{label} sent back: {record.title}',
        metadata={'record': record.pk, 'kind': label.lower()},
    )


def record_approval_note(*, record, student, note, notice_kind):
    """An approval carries no notice of its own; a note the counselor typed does."""
    if not note:
        return
    Notification.objects.create(
        student=student,
        title=APPROVAL_NOTICE_TITLE,
        message=f'{record.title}: {note}',
        kind=notice_kind,
        target_id=record.pk,
    )


REMINDER_TITLE = 'Your counselor sent a reminder'
REMINDER_COOLDOWN = timedelta(hours=12)
REMINDER_TOPICS = ('task', 'mission', 'document', 'profile')


def send_reminder(*, student, actor, topic, record_id=None):
    """Nudge a student about one thing they owe: an open task or mission, a missing document, their profile.

    Returns the student's notice, or None when the same reminder already went
    out in the last 12 hours (a second click must not pile up notices).
    Raises ValueError with a message for the counselor when the input is wrong.
    """
    record = None
    if topic == 'task':
        record = Task.objects.filter(student=student, pk=record_id, status__in=OPEN_TASK_STATUSES).first()
        kind, subject = Notification.Kind.TASK, 'task'
        message = f'“{record.title}” is due {record.due_date.isoformat()}.' if record else ''
    elif topic == 'mission':
        record = RoadmapMission.objects.filter(student=student, pk=record_id, status__in=OPEN_MISSION_STATUSES).first()
        kind, subject = Notification.Kind.TASK, 'mission'
        message = f'“{record.title}” is on your roadmap.' if record else ''
    elif topic == 'document':
        record = Document.objects.filter(
            student=student, pk=record_id, status__in=(Document.Status.REQUIRED, Document.Status.REJECTED),
        ).first()
        kind, subject = Notification.Kind.DOCUMENT, 'document'
        message = f'Please upload “{record.title}”.' if record else ''
    elif topic == 'profile':
        kind, subject = Notification.Kind.PROFILE_REVIEW, 'profile'
        message = 'Please finish your profile so your counselor can plan with you.'
    else:
        raise ValueError('Choose what to remind the student about.')
    if topic != 'profile' and record is None:
        raise ValueError('That item is no longer open.')
    target_id = record.pk if record else None
    if Notification.objects.filter(
        student=student, recipient__isnull=True, title=REMINDER_TITLE, kind=kind, target_id=target_id,
        message=message, created_at__gte=timezone.now() - REMINDER_COOLDOWN,
    ).exists():
        return None
    notice = Notification.objects.create(
        student=student, title=REMINDER_TITLE, message=message, kind=kind, target_id=target_id,
    )
    ActivityLog.objects.create(
        actor=actor, student=student, action=f'Reminder sent: {getattr(record, "title", "profile")}',
        metadata={'topic': subject, 'record': target_id},
    )
    return notice


def student_profile_defaults(school):
    """The tenant fields of a new profile: the school, and its name as displayed."""
    fallback = StudentProfile._meta.get_field('school_name').default
    return {'school': school, 'school_name': school.name if school else fallback}


def ensure_student_profile(user, *, assigned_counselor=None, actor=None):
    """Single entry point that guarantees every student account has a profile.

    Used by the Django admin, /api/users/accounts/ and quick-create so that
    onboarding, challenges and dashboards never meet a profile-less student.
    An account whose school changed is moved with ``move_student`` so the
    old school loses access.
    """
    if user.role != user.Role.STUDENT or user.is_superuser:
        return None
    school = user.school if user.school_id else None
    profile, created = StudentProfile.objects.get_or_create(
        user=user,
        defaults={**student_profile_defaults(school), 'assigned_counselor': assigned_counselor},
    )
    if not created and school and profile.school_id != school.id:
        from .tenancy import move_student

        move_student(profile, school, actor)
    return profile
