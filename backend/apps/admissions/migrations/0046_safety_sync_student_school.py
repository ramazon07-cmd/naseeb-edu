from django.db import migrations
from django.db.models import F, OuterRef, Subquery


def sync_account_school_from_profile(apps, schema_editor):
    """The profile's school is the student's tenant; align lagging account rows."""
    User = apps.get_model('users', 'User')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')
    lagging = StudentProfile.objects.filter(school__isnull=False).exclude(
        user__school_id=F('school_id'),
    ).values('user_id')
    User.objects.filter(pk__in=lagging).update(
        school_id=Subquery(StudentProfile.objects.filter(user_id=OuterRef('pk')).values('school_id')[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0045_lists_list_indexes'),
        ('users', '0012_merge_lists_admin'),
    ]

    operations = [
        migrations.RunPython(sync_account_school_from_profile, migrations.RunPython.noop),
    ]
