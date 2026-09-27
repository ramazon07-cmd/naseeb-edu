from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.admissions.models import Application, Document, Notification, StudentProfile, Task
from apps.admissions.progress import APPLICATION_DONE, late_tasks
from core.jobs import ScheduledJobCommand

LATE_TASKS = 'Late tasks require attention'
MISSING_DOCUMENTS = 'Required documents are missing'
DEADLINE = 'University deadline approaching'
TITLES = (LATE_TASKS, MISSING_DOCUMENTS, DEADLINE)
KINDS = {
    LATE_TASKS: Notification.Kind.TASK,
    MISSING_DOCUMENTS: Notification.Kind.DOCUMENT,
    DEADLINE: Notification.Kind.DEADLINE,
}


class Command(ScheduledJobCommand):
    help = 'Generate deadline, late-task and missing-document notifications (daily cron).'

    def run(self, *, batch_size, **options):
        today = timezone.localdate()
        created_or_updated = 0
        last_id = 0
        while True:
            student_ids = list(
                StudentProfile.objects.filter(pk__gt=last_id).order_by('pk').values_list('pk', flat=True)[:batch_size]
            )
            if not student_ids:
                break
            last_id = student_ids[-1]
            created_or_updated += self.refresh(student_ids, today)
        self.stdout.write(self.style.SUCCESS(f'Generated or refreshed {created_or_updated} notifications.'))

    def wanted(self, student_ids, today):
        """{(student_id, title): message} for one batch, in a fixed number of queries."""
        wanted = {}
        late = (
            Task.objects.filter(late_tasks(today), student_id__in=student_ids)
            .values('student_id').annotate(n=Count('id')).order_by()
        )
        for row in late:
            wanted[row['student_id'], LATE_TASKS] = f"{row['n']} task(s) are past their deadline."
        missing = (
            # A rejected document needs a new upload just like a missing one.
            Document.objects.filter(
                student_id__in=student_ids, status__in=[Document.Status.REQUIRED, Document.Status.REJECTED],
            )
            .values('student_id').annotate(n=Count('id')).order_by()
        )
        for row in missing:
            wanted[row['student_id'], MISSING_DOCUMENTS] = (
                f"{row['n']} required document(s) still need to be uploaded."
            )
        upcoming = (
            Application.objects.filter(student_id__in=student_ids, deadline__range=(today, today + timedelta(days=14)))
            .exclude(status__in=APPLICATION_DONE)
            .order_by('student_id', 'deadline', 'id')
            .values_list('student_id', 'deadline', 'university__name')
        )
        for student_id, deadline, university in upcoming:
            # Rows are ordered by deadline, so the first one per student is the nearest.
            wanted.setdefault((student_id, DEADLINE), f'{university} deadline is {deadline:%Y-%m-%d}.')
        return wanted

    def refresh(self, student_ids, today):
        wanted = self.wanted(student_ids, today)
        now = timezone.now()
        with transaction.atomic():
            existing = Notification.objects.filter(student_id__in=student_ids, title__in=TITLES)
            to_update, seen, resolved = [], set(), []
            for notification in existing:
                key = (notification.student_id, notification.title)
                if key not in wanted:
                    # The condition is gone: an unread alert would now be false.
                    if not notification.is_read:
                        resolved.append(notification.pk)
                    continue
                seen.add(key)
                if notification.is_read:
                    # Raised again after being read or resolved: a fresh alert,
                    # so it goes back to the top of a newest-first list.
                    notification.created_at = now
                notification.message = wanted[key]
                notification.channel = Notification.Channel.SYSTEM
                notification.kind = KINDS[notification.title]
                notification.is_read = False
                notification.updated_at = now
                to_update.append(notification)
            if resolved:
                Notification.objects.filter(pk__in=resolved).update(is_read=True, updated_at=now)
            Notification.objects.bulk_update(
                to_update, ['message', 'channel', 'kind', 'is_read', 'created_at', 'updated_at'], batch_size=500,
            )
            Notification.objects.bulk_create([
                Notification(
                    student_id=student_id, title=title, message=message,
                    channel=Notification.Channel.SYSTEM, kind=KINDS[title],
                )
                for (student_id, title), message in wanted.items() if (student_id, title) not in seen
            ], batch_size=500)
        return len(wanted)
