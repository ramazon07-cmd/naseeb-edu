from django.db import migrations, models


def map_existing_admins(apps, schema_editor):
    # Every existing product admin keeps full access.
    User = apps.get_model('users', 'User')
    User.objects.filter(models.Q(role='admin') | models.Q(is_superuser=True)).update(admin_tier='superadmin')


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_productauditevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="admin_tier",
            field=models.CharField(
                blank=True,
                choices=[
                    ("support", "Support"),
                    ("ops", "Operations"),
                    ("superadmin", "Super admin"),
                ],
                help_text="Product staff permission level. Only meaningful for admin accounts.",
                max_length=16,
            ),
        ),
        migrations.RunPython(map_existing_admins, migrations.RunPython.noop),
    ]
