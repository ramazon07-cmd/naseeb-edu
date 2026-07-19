# Generated manually for RBIS AdmitFlow
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('grade', models.CharField(choices=[('8', '8-sinf'), ('9', '9-sinf'), ('10', '10-sinf'), ('11', '11-sinf'), ('gap', 'Gap year')], default='10', max_length=10)),
                ('school', models.CharField(default='Rustam Bosimov International School', max_length=180)),
                ('gpa', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('ielts_score', models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ('sat_score', models.PositiveIntegerField(blank=True, null=True)),
                ('target_major', models.CharField(blank=True, max_length=160)),
                ('target_countries', models.CharField(blank=True, help_text='Comma-separated countries', max_length=255)),
                ('budget_usd', models.PositiveIntegerField(blank=True, null=True)),
                ('scholarship_needed', models.BooleanField(default=True)),
                ('parent_contact', models.CharField(blank=True, max_length=120)),
                ('notes', models.TextField(blank=True)),
                ('assigned_counselor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_students', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='student_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='University',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=220)),
                ('country', models.CharField(max_length=120)),
                ('city', models.CharField(blank=True, max_length=120)),
                ('website', models.URLField(blank=True)),
                ('ranking', models.PositiveIntegerField(blank=True, null=True)),
                ('application_deadline', models.DateField(blank=True, null=True)),
                ('scholarship_deadline', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['country', 'ranking', 'name'],
                'unique_together': {('name', 'country')},
            },
        ),
        migrations.CreateModel(
            name='Application',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('program', models.CharField(max_length=220)),
                ('tier', models.CharField(choices=[('dream', 'Dream'), ('target', 'Target'), ('safety', 'Safety')], default='target', max_length=20)),
                ('status', models.CharField(choices=[('researching', 'Researching'), ('shortlisted', 'Shortlisted'), ('applying', 'Applying'), ('submitted', 'Submitted'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('waitlisted', 'Waitlisted')], default='researching', max_length=30)),
                ('deadline', models.DateField(blank=True, null=True)),
                ('scholarship_deadline', models.DateField(blank=True, null=True)),
                ('application_portal_url', models.URLField(blank=True)),
                ('portal_username', models.CharField(blank=True, max_length=160)),
                ('notes', models.TextField(blank=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='applications', to='admissions.studentprofile')),
                ('university', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='applications', to='admissions.university')),
            ],
            options={
                'ordering': ['deadline', 'university__name'],
                'unique_together': {('student', 'university', 'program')},
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('description', models.TextField(blank=True)),
                ('due_date', models.DateField()),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')], default='medium', max_length=20)),
                ('status', models.CharField(choices=[('todo', 'To Do'), ('in_progress', 'In Progress'), ('submitted', 'Submitted'), ('approved', 'Approved'), ('late', 'Late')], default='todo', max_length=30)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_tasks', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to='admissions.studentprofile')),
            ],
            options={'ordering': ['due_date', '-priority']},
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('document_type', models.CharField(choices=[('passport', 'Passport'), ('transcript', 'Transcript'), ('ielts', 'IELTS'), ('sat', 'SAT'), ('cv', 'CV / Resume'), ('recommendation', 'Recommendation Letter'), ('essay', 'Essay'), ('certificate', 'Certificate'), ('other', 'Other')], default='other', max_length=40)),
                ('file', models.FileField(blank=True, null=True, upload_to='student_documents/')),
                ('status', models.CharField(choices=[('required', 'Required'), ('uploaded', 'Uploaded'), ('reviewing', 'Reviewing'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='required', max_length=30)),
                ('counselor_comment', models.TextField(blank=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='admissions.studentprofile')),
            ],
            options={'ordering': ['student__user__first_name', 'document_type']},
        ),
        migrations.CreateModel(
            name='Achievement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('category', models.CharField(choices=[('olympiad', 'Olympiad'), ('startup', 'Startup'), ('volunteering', 'Volunteering'), ('leadership', 'Leadership'), ('research', 'Research'), ('project', 'Project'), ('sport', 'Sport'), ('art', 'Art'), ('other', 'Other')], max_length=40)),
                ('description', models.TextField()),
                ('impact', models.CharField(blank=True, max_length=255)),
                ('date', models.DateField(blank=True, null=True)),
                ('proof_file', models.FileField(blank=True, null=True, upload_to='achievement_proofs/')),
                ('verified', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='achievements', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-date', 'title']},
        ),
        migrations.CreateModel(
            name='Essay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('prompt', models.TextField()),
                ('content', models.TextField(blank=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('needs_revision', 'Needs Revision'), ('reviewing', 'Reviewing'), ('approved', 'Approved')], default='draft', max_length=40)),
                ('counselor_comment', models.TextField(blank=True)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='essays', to='admissions.application')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='essays', to='admissions.studentprofile')),
            ],
            options={'ordering': ['student__user__first_name', 'status', '-updated_at']},
        ),
        migrations.CreateModel(
            name='MeetingNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('meeting_date', models.DateField(default=django.utils.timezone.localdate)),
                ('summary', models.TextField()),
                ('next_steps', models.TextField(blank=True)),
                ('counselor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='meeting_notes', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meeting_notes', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-meeting_date']},
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('message', models.TextField()),
                ('channel', models.CharField(choices=[('system', 'System'), ('email', 'Email'), ('telegram', 'Telegram')], default='system', max_length=20)),
                ('is_read', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action', models.CharField(max_length=180)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to='admissions.studentprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
