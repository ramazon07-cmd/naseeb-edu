from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0009_xp_and_leveling'),
    ]

    operations = [
        migrations.CreateModel(
            name='MessageChannel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('direct', 'Direct'), ('group', 'Group'), ('community', 'Community'), ('discussion', 'Discussion')], max_length=20)),
                ('name', models.CharField(blank=True, max_length=180)),
                ('description', models.TextField(blank=True)),
                ('direct_key', models.CharField(blank=True, max_length=80, null=True, unique=True)),
                ('is_public', models.BooleanField(default=False)),
                ('is_archived', models.BooleanField(default=False)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_message_channels', to=settings.AUTH_USER_MODEL)),
                ('school', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='message_channels', to='admissions.school')),
            ],
            options={
                'ordering': ['-last_message_at', '-updated_at'],
                'indexes': [
                    models.Index(fields=['kind', 'school', 'is_public'], name='msg_channel_discovery_idx'),
                    models.Index(fields=['last_message_at'], name='msg_channel_recent_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ChannelMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('owner', 'Owner'), ('moderator', 'Moderator'), ('member', 'Member')], default='member', max_length=20)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('last_read_at', models.DateTimeField(blank=True, null=True)),
                ('notifications_enabled', models.BooleanField(default=True)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='admissions.messagechannel')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['joined_at', 'id'],
                'indexes': [models.Index(fields=['user', 'channel'], name='msg_member_lookup_idx')],
                'constraints': [models.UniqueConstraint(fields=('channel', 'user'), name='unique_channel_membership')],
            },
        ),
        migrations.CreateModel(
            name='ChannelMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('body', models.TextField()),
                ('is_anonymous', models.BooleanField(default=False)),
                ('is_edited', models.BooleanField(default=False)),
                ('is_accepted_answer', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='admissions.messagechannel')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='replies', to='admissions.channelmessage')),
                ('sender', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='channel_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at', 'id'],
                'indexes': [
                    models.Index(fields=['channel', '-created_at'], name='msg_channel_timeline_idx'),
                    models.Index(fields=['parent', 'created_at'], name='msg_thread_reply_idx'),
                ],
            },
        ),
    ]
