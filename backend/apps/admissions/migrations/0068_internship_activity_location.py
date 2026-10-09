from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissions', '0067_record_created_by')]

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
