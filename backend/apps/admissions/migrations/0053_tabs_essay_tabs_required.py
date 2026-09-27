from django.db import migrations, models
import django.db.models.deletion


# Separate from 0052: PostgreSQL can't ALTER a table that still has pending
# deferred FK checks from the data move in the same transaction.
class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0052_tabs_essay_tabs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="essaycheckpoint",
            name="tab",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="checkpoints",
                to="admissions.essaytab",
            ),
        ),
        migrations.AlterField(
            model_name="essaydepthcheck",
            name="tab",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="depth_checks",
                to="admissions.essaytab",
            ),
        ),
        migrations.RemoveField(
            model_name="essay",
            name="doc",
        ),
        migrations.RemoveField(
            model_name="essay",
            name="last_client_save_id",
        ),
        migrations.RemoveField(
            model_name="essay",
            name="last_cursor",
        ),
        migrations.RemoveField(
            model_name="essay",
            name="save_seq",
        ),
    ]
