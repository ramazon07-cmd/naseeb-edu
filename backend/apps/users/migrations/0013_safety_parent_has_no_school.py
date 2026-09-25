from django.db import migrations, models


def detach_parents_from_schools(apps, schema_editor):
    """A parent's school was copied from their first child; it granted tenant access."""
    User = apps.get_model('users', 'User')
    User.objects.filter(role='parent', school__isnull=False).update(school=None)


class Migration(migrations.Migration):
    # PostgreSQL refuses ALTER TABLE while the update's deferred foreign-key
    # checks are pending in the same transaction.
    atomic = False

    dependencies = [
        ("users", "0012_merge_lists_admin"),
    ]

    operations = [
        migrations.RunPython(detach_parents_from_schools, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("role", "parent"), _negated=True),
                    ("school__isnull", True),
                    _connector="OR",
                ),
                name="parent_has_no_school",
            ),
        ),
    ]
