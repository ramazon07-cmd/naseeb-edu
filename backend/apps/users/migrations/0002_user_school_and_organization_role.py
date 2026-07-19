from django.db import migrations, models
import django.db.models.deletion


def assign_existing_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')
    School = apps.get_model('admissions', 'School')
    school = School.objects.filter(code='rbis').first()
    if not school:
        return
    User.objects.filter(role='student', school__isnull=True).update(school=school)
    for profile in StudentProfile.objects.select_related('user').filter(school=school):
        if profile.user_id:
            User.objects.filter(id=profile.user_id, school__isnull=True).update(school=school)


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0002_school_organization'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='users',
                to='admissions.school',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('counselor', 'Counselor'),
                    ('organization', 'Organization School'),
                    ('student', 'Student'),
                    ('parent', 'Parent'),
                ],
                default='student',
                max_length=20,
            ),
        ),
        migrations.RunPython(assign_existing_users, migrations.RunPython.noop),
    ]
