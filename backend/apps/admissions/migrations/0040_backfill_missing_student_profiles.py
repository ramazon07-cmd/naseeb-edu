from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    """Student accounts created via /register/ or /accounts/ never got a profile (BE-M3)."""
    User = apps.get_model('users', 'User')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')
    School = apps.get_model('admissions', 'School')
    missing = User.objects.filter(role='student', is_superuser=False, student_profile__isnull=True)
    for user in missing.iterator():
        school = School.objects.filter(pk=user.school_id).first() if user.school_id else None
        StudentProfile.objects.create(
            user=user,
            school=school,
            school_name=school.name if school else 'Naseeb Edu',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0039_studentprofile_gpa_scale'),
        ('users', '0006_productauditevent'),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, migrations.RunPython.noop),
    ]
