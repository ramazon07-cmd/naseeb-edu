from django.db import migrations, models


def mark_days_met_by_words(apps, schema_editor):
    Day = apps.get_model('admissions', 'EssayWritingDay')
    Day.objects.filter(words_peak__gte=100, goal_met=False).update(goal_met=True)


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0085_essay_writing_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='essaywritingday',
            name='active_seconds',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(mark_days_met_by_words, migrations.RunPython.noop),
    ]
