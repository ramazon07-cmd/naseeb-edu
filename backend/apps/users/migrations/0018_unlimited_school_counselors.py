from django.db import migrations


def unlimited_school_counselors(apps, schema_editor):
    # Issue #52: restore paid plan limits when payments ship (D4 / S2.1).
    apps.get_model('users', 'Plan').objects.using(schema_editor.connection.alias).filter(
        code='school-standard',
    ).update(max_counselors=None)


def restore_school_limit(apps, schema_editor):
    apps.get_model('users', 'Plan').objects.using(schema_editor.connection.alias).filter(
        code='school-standard', max_counselors__isnull=True,
    ).update(max_counselors=3)


class Migration(migrations.Migration):
    dependencies = [('users', '0017_revoked_refresh_session')]
    operations = [migrations.RunPython(unlimited_school_counselors, restore_school_limit)]
