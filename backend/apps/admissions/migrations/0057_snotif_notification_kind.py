from django.db import migrations, models

# Titles written by the code paths that existed before notices carried a kind.
KIND_BY_TITLE = {
    'Late tasks require attention': 'task',
    'Required documents are missing': 'document',
    'University deadline approaching': 'deadline',
    'Essay shared with counselor': 'essay',
    'Deadline alert': 'task',
}


def backfill_kinds(apps, schema_editor):
    Notification = apps.get_model('admissions', 'Notification')
    for title, kind in KIND_BY_TITLE.items():
        Notification.objects.filter(title=title).update(kind=kind)
    Notification.objects.filter(title__startswith='Meeting ').update(kind='meeting')


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0056_sroad_booking_cancelled'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='kind',
            field=models.CharField(
                choices=[
                    ('general', 'General'), ('task', 'Task'), ('document', 'Document'), ('deadline', 'Deadline'),
                    ('essay', 'Essay'), ('meeting', 'Meeting'), ('message', 'Message'),
                ],
                default='general',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='target_id',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_kinds, migrations.RunPython.noop),
    ]
