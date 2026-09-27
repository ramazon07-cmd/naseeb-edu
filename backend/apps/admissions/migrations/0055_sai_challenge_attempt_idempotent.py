from datetime import timedelta

from django.db import migrations, models
from django.db.models import Count


def separate_identical_completions(apps, schema_editor):
    """Rows that share a completion time get distinct ones (a microsecond apart),
    so the unique constraint can be added without losing any attempt."""
    ChallengeAttempt = apps.get_model('admissions', 'ChallengeAttempt')
    clashes = (ChallengeAttempt.objects.values('student_id', 'challenge', 'completed_at')
               .annotate(n=Count('id')).filter(n__gt=1))
    for clash in clashes.iterator():
        rows = ChallengeAttempt.objects.filter(
            student_id=clash['student_id'], challenge=clash['challenge'], completed_at=clash['completed_at'],
        ).order_by('id')
        for offset, row in enumerate(rows[1:], start=1):
            ChallengeAttempt.objects.filter(pk=row.pk).update(
                completed_at=row.completed_at + timedelta(microseconds=offset))


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0054_share_essay_sharing'),
    ]

    operations = [
        migrations.RunPython(separate_identical_completions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='challengeattempt',
            constraint=models.UniqueConstraint(
                fields=('student', 'challenge', 'completed_at'),
                name='unique_challenge_attempt_completion',
            ),
        ),
    ]
