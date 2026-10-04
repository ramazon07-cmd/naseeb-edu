from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0062_s3_booking_previous_time'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MeetingAvailability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('starts_at', models.DateTimeField()),
                ('duration_minutes', models.PositiveSmallIntegerField(default=45)),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meeting_availability', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['starts_at', 'id']},
        ),
        migrations.AddConstraint(
            model_name='meetingavailability',
            constraint=models.UniqueConstraint(fields=('participant', 'starts_at'), name='unique_meeting_availability_start'),
        ),
        migrations.AddField(
            model_name='booking',
            name='availability_slot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bookings', to='admissions.meetingavailability'),
        ),
    ]
