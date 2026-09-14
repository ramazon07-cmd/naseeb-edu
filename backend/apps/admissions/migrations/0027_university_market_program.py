import django.db.models.deletion
from django.db import migrations, models


def populate_university_markets(apps, schema_editor):
    University = apps.get_model('admissions', 'University')
    aliases = {
        'us': {'usa', 'united states', 'united states of america'},
        'canada': {'canada'},
        'china': {'china', 'mainland china'},
        'hong_kong': {'hong kong', 'hong kong sar'},
    }
    for university in University.objects.all().only('id', 'country'):
        country = (university.country or '').strip().lower()
        market = next((key for key, values in aliases.items() if country in values), '')
        if market:
            University.objects.filter(pk=university.pk).update(market=market)


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0026_challengeattempt'),
    ]

    operations = [
        migrations.AddField(
            model_name='university',
            name='market',
            field=models.CharField(
                blank=True,
                choices=[
                    ('us', 'United States'),
                    ('canada', 'Canada'),
                    ('china', 'China'),
                    ('hong_kong', 'Hong Kong'),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='university',
            name='catalog_source_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='university',
            name='catalog_verified_at',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='UniversityProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=220)),
                ('canonical_major', models.CharField(db_index=True, max_length=160)),
                ('degree_level', models.CharField(choices=[('bachelor', "Bachelor's")], default='bachelor', max_length=20)),
                ('teaching_language', models.CharField(default='English', max_length=80)),
                ('duration_years', models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ('tuition_usd', models.PositiveIntegerField(blank=True, null=True)),
                ('estimated_living_cost_usd', models.PositiveIntegerField(blank=True, null=True)),
                ('min_gpa', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('sat_min', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('ielts_min', models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ('toefl_min', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('application_deadline', models.DateField(blank=True, null=True)),
                ('scholarship_deadline', models.DateField(blank=True, null=True)),
                ('application_url', models.URLField(blank=True)),
                ('source_url', models.URLField(blank=True)),
                ('verified_at', models.DateField(blank=True, null=True)),
                ('international_students_eligible', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('university', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='programs', to='admissions.university')),
            ],
            options={
                'ordering': ['university__name', 'canonical_major', 'name'],
                'constraints': [
                    models.UniqueConstraint(fields=('university', 'name', 'degree_level'), name='unique_university_program_degree'),
                ],
            },
        ),
        migrations.RunPython(populate_university_markets, migrations.RunPython.noop),
    ]
