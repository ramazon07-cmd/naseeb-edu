from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissions', '0066_university_qs_data')]

    operations = [
        migrations.AddField(
            model_name='internship',
            name='location',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='activity',
            name='location',
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
