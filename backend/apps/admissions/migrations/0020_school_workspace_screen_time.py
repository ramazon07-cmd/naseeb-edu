import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0019_supportticket'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='workspace_type',
            field=models.CharField(choices=[('school', 'Organization school'), ('individual', 'Individual counselor workspace')], default='school', max_length=20),
        ),
        migrations.AddField(
            model_name='school',
            name='owner_counselor',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_counselor_workspace', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='ScreenTimeDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('page', models.CharField(max_length=80)),
                ('active_seconds', models.PositiveIntegerField(default=0)),
                ('sessions', models.PositiveIntegerField(default=0)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='screen_time_days', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-active_seconds', 'page'],
                'indexes': [models.Index(fields=['date', 'user'], name='screen_time_date_user_idx')],
                'constraints': [models.UniqueConstraint(fields=('user', 'date', 'page'), name='unique_screen_time_user_day_page')],
            },
        ),
    ]
