from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('admissions', '0065_university_ranking_label')]

    operations = [
        migrations.AddField(
            model_name='university',
            name='qs_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
