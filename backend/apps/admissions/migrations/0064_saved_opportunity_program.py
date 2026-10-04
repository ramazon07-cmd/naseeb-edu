from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('admissions', '0063_meeting_availability'),
    ]

    operations = [
        migrations.CreateModel(
            name='SavedOpportunityProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_by_students', to='admissions.opportunityprogram')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_opportunity_programs', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='savedopportunityprogram',
            constraint=models.UniqueConstraint(fields=('student', 'program'), name='unique_student_saved_opportunity_program'),
        ),
    ]
