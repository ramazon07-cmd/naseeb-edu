from django.db import migrations, models
from django.db.models import Exists, F, OuterRef, Q


def share_engaged_essays(apps, schema_editor):
    """Keep counselor access to essays a counselor already worked on.

    Engaged means: moved past draft, carries counselor feedback, or has a
    revision written by someone other than the student. Everything else
    becomes private to the student.
    """
    Essay = apps.get_model('admissions', 'Essay')
    EssayRevision = apps.get_model('admissions', 'EssayRevision')
    staff_revision = EssayRevision.objects.filter(essay_id=OuterRef('pk'), created_by__isnull=False).exclude(
        created_by_id=OuterRef('student__user_id'),
    )
    Essay.objects.filter(
        ~Q(status='draft') | ~Q(counselor_comment='') | Exists(staff_revision),
    ).update(shared_with_counselor=True, shared_at=F('updated_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0053_tabs_essay_tabs_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='essay',
            name='shared_with_counselor',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='essay',
            name='shared_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='essay',
            index=models.Index(fields=['student', 'shared_with_counselor'], name='essay_student_shared_idx'),
        ),
        migrations.RunPython(share_engaged_essays, migrations.RunPython.noop),
    ]
