from django.db import migrations, models
import django.db.models.deletion


def assign_default_school(apps, schema_editor):
    School = apps.get_model('admissions', 'School')
    StudentProfile = apps.get_model('admissions', 'StudentProfile')
    school, _ = School.objects.get_or_create(
        code='rbis',
        defaults={'name': 'RBIS', 'is_active': True},
    )
    StudentProfile.objects.filter(school__isnull=True).update(school=school)


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=180, unique=True)),
                ('code', models.SlugField(max_length=80, unique=True)),
                ('contact_email', models.EmailField(blank=True, max_length=254)),
                ('contact_phone', models.CharField(blank=True, max_length=32)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.RenameField(
            model_name='studentprofile',
            old_name='school',
            new_name='school_name',
        ),
        migrations.AlterField(
            model_name='studentprofile',
            name='school_name',
            field=models.CharField(default='RBIS', max_length=180),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='students',
                to='admissions.school',
            ),
        ),
        migrations.RunPython(assign_default_school, migrations.RunPython.noop),
    ]
