from django.core.management.base import BaseCommand, CommandError
from django.db import models

from apps.admissions.models import StudentProfile
from apps.users.models import User


class Command(BaseCommand):
    help = 'Audit counselor school membership and assigned-student school consistency.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-issues',
            action='store_true',
            help='Exit with an error when missing or mismatched school links are found.',
        )

    def handle(self, *args, **options):
        missing = User.objects.filter(role=User.Role.COUNSELOR, school__isnull=True)
        mismatched = StudentProfile.objects.filter(
            assigned_counselor__isnull=False,
        ).exclude(school_id=models.F('assigned_counselor__school_id')).select_related(
            'user', 'school', 'assigned_counselor', 'assigned_counselor__school'
        )

        for counselor in missing:
            self.stdout.write(f'MISSING counselor={counselor.id} username={counselor.username}')
        for student in mismatched:
            self.stdout.write(
                'MISMATCH '
                f'student={student.id} counselor={student.assigned_counselor_id} '
                f'student_school={student.school_id} counselor_school={student.assigned_counselor.school_id}'
            )

        issue_count = missing.count() + mismatched.count()
        if issue_count:
            message = f'Counselor-school audit found {issue_count} issue(s).'
            if options['fail_on_issues']:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))
            return
        self.stdout.write(self.style.SUCCESS('Counselor-school audit passed.'))
