import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0020_google_account'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefreshRotation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_jti', models.CharField(max_length=64, unique=True)),
                ('sid', models.CharField(db_index=True, max_length=64)),
                ('user_id', models.BigIntegerField()),
                ('rotated_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('reuses', models.PositiveSmallIntegerField(default=0)),
            ],
        ),
    ]
