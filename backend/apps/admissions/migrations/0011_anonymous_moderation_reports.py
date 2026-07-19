from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0010_scalable_messaging'),
    ]

    operations = [
        migrations.AddField(
            model_name='channelmembership',
            name='muted_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='MessageReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reason', models.CharField(choices=[('spam', 'Spam'), ('harassment', 'Harassment or bullying'), ('unsafe', 'Unsafe content'), ('privacy', 'Privacy concern'), ('misinformation', 'Misinformation'), ('other', 'Other')], max_length=30)),
                ('details', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('reviewing', 'Reviewing'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], default='pending', max_length=20)),
                ('action', models.CharField(choices=[('none', 'No action'), ('content_removed', 'Content removed'), ('muted_24h', 'Member muted for 24 hours'), ('muted_7d', 'Member muted for 7 days')], default='none', max_length=30)),
                ('moderator_note', models.TextField(blank=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='admissions.channelmessage')),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='message_reports', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_message_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['status', '-created_at'], name='msg_report_status_idx'), models.Index(fields=['message', 'status'], name='msg_report_message_idx')],
                'constraints': [models.UniqueConstraint(fields=('message', 'reporter'), name='unique_message_reporter')],
            },
        ),
    ]
