from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_booking_statuses(apps, schema_editor):
    Booking = apps.get_model('admissions', 'Booking')
    status_map = {
        'requested': 'pending',
        'confirmed': 'approved',
        'cancelled': 'rejected',
    }
    for old_status, new_status in status_map.items():
        Booking.objects.filter(status=old_status).update(status=new_status)


def reverse_booking_statuses(apps, schema_editor):
    Booking = apps.get_model('admissions', 'Booking')
    status_map = {
        'pending': 'requested',
        'approved': 'confirmed',
        'rejected': 'cancelled',
    }
    for new_status, old_status in status_map.items():
        Booking.objects.filter(status=new_status).update(status=old_status)


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0015_remove_roadmapmission_progress_percent'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='booking',
            old_name='counselor',
            new_name='participant',
        ),
        migrations.AlterField(
            model_name='booking',
            name='participant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='meeting_bookings',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(migrate_booking_statuses, reverse_booking_statuses),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('completed', 'Completed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
