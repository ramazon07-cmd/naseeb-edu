from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.admissions.models import Application, Document, Notification, StudentProfile, Task


class Command(BaseCommand):
    help = 'Generate deadline, late-task and missing-document notifications.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        created_or_updated = 0

        for student in StudentProfile.objects.select_related('user').all():
            late_tasks = Task.objects.filter(student=student, due_date__lt=today).exclude(status=Task.Status.APPROVED)
            if late_tasks.exists():
                Notification.objects.update_or_create(
                    student=student,
                    title='Late tasks require attention',
                    defaults={
                        'message': f'{late_tasks.count()} task(s) are past their deadline.',
                        'channel': Notification.Channel.SYSTEM,
                        'is_read': False,
                    },
                )
                created_or_updated += 1

            missing_docs = Document.objects.filter(student=student, status=Document.Status.REQUIRED)
            if missing_docs.exists():
                Notification.objects.update_or_create(
                    student=student,
                    title='Required documents are missing',
                    defaults={
                        'message': f'{missing_docs.count()} required document(s) still need to be uploaded.',
                        'channel': Notification.Channel.SYSTEM,
                        'is_read': False,
                    },
                )
                created_or_updated += 1

            upcoming = Application.objects.filter(
                student=student,
                deadline__range=(today, today + timedelta(days=14)),
            ).exclude(status__in=[Application.Status.SUBMITTED, Application.Status.ACCEPTED, Application.Status.REJECTED])
            if upcoming.exists():
                nearest = upcoming.order_by('deadline').first()
                Notification.objects.update_or_create(
                    student=student,
                    title='University deadline approaching',
                    defaults={
                        'message': f'{nearest.university.name} deadline is {nearest.deadline:%Y-%m-%d}.',
                        'channel': Notification.Channel.SYSTEM,
                        'is_read': False,
                    },
                )
                created_or_updated += 1

        self.stdout.write(self.style.SUCCESS(f'Generated or refreshed {created_or_updated} notifications.'))
