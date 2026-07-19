from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0007_opportunityprogram_university_acceptance_rate_and_more'),
        ('users', '0003_user_teacher_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='roadmapmission',
            name='assigned_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_roadmap_missions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='roadmapmission',
            name='status',
            field=models.CharField(
                choices=[
                    ('planned', 'Planned'),
                    ('in_progress', 'In Progress'),
                    ('submitted', 'Submitted for approval'),
                    ('completed', 'Completed'),
                ],
                default='planned',
                max_length=30,
            ),
        ),
    ]
