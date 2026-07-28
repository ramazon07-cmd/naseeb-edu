from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import RoadmapMission, StudentProfile, XPTransaction


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
