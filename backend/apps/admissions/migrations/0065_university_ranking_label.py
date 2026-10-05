from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0064_saved_opportunity_program'),
    ]

    operations = [
        migrations.AddField(
            model_name='university',
            name='ranking_label',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
