from django.db import migrations, models
import django.db.models.deletion


def sequence_existing_missions(apps, schema_editor):
    RoadmapMission = apps.get_model('admissions', 'RoadmapMission')
    student_ids = RoadmapMission.objects.values_list('student_id', flat=True).distinct()
    for student_id in student_ids:
        mission_ids = RoadmapMission.objects.filter(student_id=student_id).order_by('created_at', 'id').values_list('id', flat=True)
        for sequence, mission_id in enumerate(mission_ids, start=1):
            RoadmapMission.objects.filter(pk=mission_id).update(sequence=sequence)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('admissions', '0013_activity_google_docs_url_honor_google_docs_url_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='roadmapmission',
            name='level',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='roadmapmission',
            name='sequence',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='roadmapmission',
            name='prerequisite',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unlocked_missions', to='admissions.roadmapmission'),
        ),
        migrations.RunPython(sequence_existing_missions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='roadmapmission',
            options={'ordering': ['level', 'sequence', 'id']},
        ),
    ]
