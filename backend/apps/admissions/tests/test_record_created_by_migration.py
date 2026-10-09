"""0067: essays created by staff (first legacy revision by someone other than the student) get created_by."""
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RecordCreatedByMigrationTests(TransactionTestCase):
    migrate_from = [('admissions', '0066_university_qs_data')]
    migrate_to = [('admissions', '0067_record_created_by')]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        cache.clear()

    def test_staff_created_essays_are_backfilled(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old = executor.loader.project_state(self.migrate_from).apps
        School, User = old.get_model('admissions', 'School'), old.get_model('users', 'User')
        Profile, Essay = old.get_model('admissions', 'StudentProfile'), old.get_model('admissions', 'Essay')
        Revision = old.get_model('admissions', 'EssayRevision')
        school = School.objects.create(name='Backfill school', code='backfill-school')
        student_user = User.objects.create(username='bf-student', email='bf-s@example.com', role='student', school=school)
        counselor = User.objects.create(username='bf-counselor', email='bf-c@example.com', role='counselor', school=school)
        student = Profile.objects.create(user=student_user, school=school)
        assigned = Essay.objects.create(student=student, title='Assigned', prompt='', content='')
        own = Essay.objects.create(student=student, title='Own', prompt='', content='')
        Essay.objects.create(student=student, title='Lab', prompt='', content='')  # no legacy revision at all
        Revision.objects.create(essay=assigned, version=1, created_by=counselor)
        Revision.objects.create(essay=assigned, version=2, created_by=student_user)
        Revision.objects.create(essay=own, version=1, created_by=student_user)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        Essay = executor.loader.project_state(self.migrate_to).apps.get_model('admissions', 'Essay')
        self.assertEqual(
            dict(Essay.objects.values_list('title', 'created_by_id')),
            {'Assigned': counselor.pk, 'Own': None, 'Lab': None},
        )
