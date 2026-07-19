from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0004_applicationstatushistory_essayrevision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='studentprofile',
            name='school_name',
            field=models.CharField(default='Naseeb Edu', max_length=180),
        ),
    ]
