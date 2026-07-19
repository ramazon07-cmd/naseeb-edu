from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0008_roadmap_staff_control'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentprofile',
            name='level',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='xp_total',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='LevelApproval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_level', models.PositiveSmallIntegerField()),
                ('to_level', models.PositiveSmallIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_student_levels', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='level_approvals', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.CreateModel(
            name='XPTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_type', models.CharField(choices=[('task', 'Task approval'), ('roadmap', 'Roadmap approval')], max_length=20)),
                ('source_id', models.PositiveBigIntegerField()),
                ('amount', models.PositiveIntegerField()),
                ('reason', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('awarded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='awarded_xp_transactions', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='xp_transactions', to='admissions.studentprofile')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'constraints': [models.UniqueConstraint(fields=('source_type', 'source_id'), name='unique_xp_per_approved_work')],
            },
        ),
    ]
