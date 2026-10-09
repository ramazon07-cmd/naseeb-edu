from django.db import migrations, models

from apps.admissions.search_text import university_search_text


def fill_search_text(apps, schema_editor):
    University = apps.get_model('admissions', 'University')
    rows = list(University.objects.only('id', 'name', 'city', 'country'))
    for row in rows:
        row.search_text = university_search_text(row.name, row.city, row.country)
    University.objects.bulk_update(rows, ['search_text'], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [('admissions', '0068_internship_activity_location')]

    operations = [
        migrations.AddField(
            model_name='university',
            name='search_text',
            field=models.TextField(blank=True, default='', editable=False),
        ),
        migrations.RunPython(fill_search_text, migrations.RunPython.noop),
    ]
