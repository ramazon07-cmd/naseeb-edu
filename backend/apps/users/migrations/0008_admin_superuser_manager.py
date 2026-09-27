import apps.users.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_admin_staff_tiers"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="user",
            managers=[
                ("objects", apps.users.models.UserManager()),
            ],
        ),
    ]
