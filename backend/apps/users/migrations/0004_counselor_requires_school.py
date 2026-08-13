from django.db import migrations, models
import django.db.models.deletion


FALLBACK_SCHOOL_CODE = 'legacy-counselor-workspace'


def backfill_counselor_schools(apps, schema_editor):
    User = apps.get_model('users', 'User')
    School = apps.get_model('admissions', 'School')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')

    counselors = User.objects.filter(role='counselor', school__isnull=True).order_by('id')
    single_active_school = None
    active_school_ids = list(School.objects.filter(is_active=True).values_list('id', flat=True)[:2])
    if len(active_school_ids) == 1:
        single_active_school = School.objects.get(id=active_school_ids[0])

    fallback_school = None
    for counselor in counselors.iterator():
        assigned_school_ids = list(
            StudentProfile.objects.filter(
                assigned_counselor_id=counselor.id,
                school__isnull=False,
            ).values_list('school_id', flat=True).distinct()[:2]
        )
        if len(assigned_school_ids) == 1:
            school_id = assigned_school_ids[0]
        elif single_active_school:
            school_id = single_active_school.id
        else:
            if fallback_school is None:
                fallback_school = School.objects.filter(code=FALLBACK_SCHOOL_CODE).first()
                if fallback_school is None:
                    fallback_school = School.objects.filter(name='Legacy Counselor Workspace').first()
                if fallback_school is None:
                    fallback_school = School.objects.create(
                        code=FALLBACK_SCHOOL_CODE,
                        name='Legacy Counselor Workspace',
                        is_active=False,
                    )
            school_id = fallback_school.id
        User.objects.filter(id=counselor.id).update(school_id=school_id)


class Migration(migrations.Migration):

    # PostgreSQL defers the FK trigger events produced by the data backfill until
    # transaction commit. The following ALTER TABLE / constraint operations must
    # therefore run after that commit instead of inside one migration transaction.
    atomic = False

    dependencies = [
        ('admissions', '0019_supportticket'),
        ('users', '0003_user_teacher_role'),
    ]

    operations = [
        migrations.RunPython(backfill_counselor_schools, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='users',
                to='admissions.school',
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=~models.Q(role='counselor') | models.Q(school__isnull=False),
                name='counselor_requires_school',
            ),
        ),
    ]
