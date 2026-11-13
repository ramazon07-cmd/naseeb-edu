"""Composite indexes for a staff member's meetings and a counselor's students.

Both tables are large in production, so the indexes are built CONCURRENTLY on PostgreSQL
(no write lock while instances boot); that needs a non-atomic migration.
"""
from django.db import migrations, models

from core.migration_ops import AddIndexOnline


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('admissions', '0090_meeting_email_outbox'),
    ]

    operations = [
        AddIndexOnline(
            model_name='booking',
            index=models.Index(fields=['participant', 'status', 'starts_at'], name='booking_part_status_start_idx'),
        ),
        AddIndexOnline(
            model_name='studentprofile',
            index=models.Index(fields=['assigned_counselor', 'school'], name='student_counselor_school_idx'),
        ),
    ]
