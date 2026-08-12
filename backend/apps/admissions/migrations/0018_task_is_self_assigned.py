from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0017_backfill_missing_student_profiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='is_self_assigned',
            field=models.BooleanField(
                default=False,
                help_text='Student-created personal task. Self-assigned tasks never award XP.',
            ),
        ),
    ]
