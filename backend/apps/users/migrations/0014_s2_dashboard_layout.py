from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_safety_parent_has_no_school"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="dashboard_layout",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
