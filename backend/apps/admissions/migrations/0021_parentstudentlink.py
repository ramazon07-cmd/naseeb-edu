import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0020_school_workspace_screen_time'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ParentStudentLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('relationship', models.CharField(choices=[('mother', 'Mother'), ('father', 'Father'), ('guardian', 'Guardian'), ('other', 'Other')], default='guardian', max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Awaiting parent consent'), ('active', 'Active'), ('revoked', 'Revoked')], default='pending', max_length=20)),
                ('can_view_applications', models.BooleanField(default=True)),
                ('can_view_documents', models.BooleanField(default=True)),
                ('can_view_meetings', models.BooleanField(default=True)),
                ('invited_at', models.DateTimeField(auto_now_add=True)),
                ('consented_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('invited_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='parent_links_invited', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_links', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='parent_links', to='admissions.studentprofile')),
            ],
            options={
                'ordering': ['student__user__first_name', 'student__user__last_name', 'id'],
                'indexes': [
                    models.Index(fields=['parent', 'status'], name='parent_link_parent_status_idx'),
                    models.Index(fields=['student', 'status'], name='parent_link_student_status_idx'),
                ],
                'constraints': [models.UniqueConstraint(fields=('parent', 'student'), name='unique_parent_student_link')],
            },
        ),
    ]
