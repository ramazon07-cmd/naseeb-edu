from django.db import migrations


class Migration(migrations.Migration):
    """Emptied when this branch merged main.

    Both branches removed the Resource Index independently, so ResourceLibraryItem
    was deleted twice: here, and again in 0028_delete_resourcelibraryitem on main.
    Two DeleteModel operations on one model break the migration state, and main's
    copy is the one production has already applied, so that one keeps the work and
    this one becomes a no-op. Environments that recorded this migration are
    unaffected; a fresh database gets the delete from 0028.
    """

    dependencies = [("admissions", "0026_challengeattempt")]

    operations = []
