from django.db import migrations


def delete_parent_rows(apps, schema_editor):
    # Parents have no Screen Time; these rows were recorded by mistake and have no use.
    apps.get_model('admissions', 'ScreenTimeDaily').objects.using(schema_editor.connection.alias).filter(user__role='parent').delete()


class Migration(migrations.Migration):
    dependencies = [('admissions', '0078_student_invites')]

    operations = [migrations.RunPython(delete_parent_rows, migrations.RunPython.noop)]
