from django.db import migrations


def create_missing_student_profiles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')
    missing_students = User.objects.filter(
        role='student',
        is_superuser=False,
        student_profile__isnull=True,
    ).select_related('school')
    StudentProfile.objects.bulk_create([
        StudentProfile(
            user_id=user.id,
            school_id=user.school_id,
            school_name=user.school.name if user.school_id else 'Naseeb Edu',
            xp_total=0,
            level=1,
        )
        for user in missing_students
    ], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0016_booking_participant_and_approval'),
    ]

    operations = [
        migrations.RunPython(create_missing_student_profiles, migrations.RunPython.noop),
    ]
