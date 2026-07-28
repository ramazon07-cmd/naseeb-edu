from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0014_roadmap_level_sequence_prerequisite'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='roadmapmission',
            name='progress_percent',
        ),
    ]
