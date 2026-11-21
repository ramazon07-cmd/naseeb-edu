from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('telegram_bot', '0003_staff_access_student_link_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='studenttelegram',
            name='telegram_username',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='telegramoutbox',
            name='buttons',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
