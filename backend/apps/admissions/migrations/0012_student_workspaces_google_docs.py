from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0011_anonymous_moderation_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='student_response',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='task',
            name='submission_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='task',
            name='submission_file',
            field=models.FileField(blank=True, null=True, upload_to='task_submissions/'),
        ),
        migrations.AddField(
            model_name='task',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='google_docs_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='essay',
            name='google_docs_url',
            field=models.URLField(blank=True),
        ),
    ]
