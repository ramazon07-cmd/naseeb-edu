from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_school_and_organization_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('counselor', 'Counselor'),
                    ('teacher', 'Teacher'),
                    ('organization', 'Organization School'),
                    ('student', 'Student'),
                    ('parent', 'Parent'),
                ],
                default='student',
                max_length=20,
            ),
        ),
    ]
