from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("admissions", "0026_challengeattempt")]

    operations = [migrations.DeleteModel(name="ResourceLibraryItem")]
