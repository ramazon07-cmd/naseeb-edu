from django.db import migrations


FEATURES = ('ai_assistant', 'essay_coach', 'parent_portal', 'reports', 'organization_accounts')
ALL = {key: True for key in FEATURES}

# Frozen copy of entitlements.DEFAULT_PLANS at the time of this migration.
PLANS = {
    'school-standard': {
        'name': 'School Standard',
        'description': 'Organization school workspace.',
        'max_counselors': 3,
        'max_students': None,
        'max_teachers': None,
        'features': ALL,
    },
    'individual-counselor': {
        'name': 'Individual Counselor',
        'description': 'Private workspace for one counselor.',
        'max_counselors': 1,
        'max_students': None,
        'max_teachers': 0,
        'features': {**ALL, 'organization_accounts': False},
    },
    'center': {
        'name': 'Center',
        'description': 'Education center or counseling agency with several counselors.',
        'max_counselors': None,
        'max_students': None,
        'max_teachers': None,
        'features': ALL,
    },
}


def seed(apps, schema_editor):
    Plan = apps.get_model('users', 'Plan')
    WorkspaceSubscription = apps.get_model('users', 'WorkspaceSubscription')
    School = apps.get_model('admissions', 'School')

    plans = {}
    for code, values in PLANS.items():
        plans[code], _ = Plan.objects.get_or_create(code=code, defaults=values)

    covered = set(WorkspaceSubscription.objects.values_list('school_id', flat=True))
    WorkspaceSubscription.objects.bulk_create([
        WorkspaceSubscription(
            school_id=school_id,
            plan=plans['individual-counselor' if workspace_type == 'individual' else 'school-standard'],
            status='active',
        )
        for school_id, workspace_type in School.objects.values_list('id', 'workspace_type').iterator()
        if school_id not in covered
    ], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0009_admin_plans'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
