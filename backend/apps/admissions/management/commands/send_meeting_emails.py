from django.core.management.base import BaseCommand

from apps.admissions.meeting_mail import SEND_BATCH, deliver_queued_emails


class Command(BaseCommand):
    help = (
        'Send queued meeting emails (the counselor bot asks the backend for this every minute; '
        'run it by hand, or from a cron, where no bot runs).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=SEND_BATCH)
        parser.add_argument('--seconds', type=float, default=None, help='Time budget (default MEETING_EMAIL_SEND_SECONDS).')

    def handle(self, *args, **options):
        counts = deliver_queued_emails(budget=options['seconds'], limit=max(1, options['limit']))
        self.stdout.write(self.style.SUCCESS(
            'Meeting emails: {sent} sent, {failed} to retry, {dropped} dropped, {waiting} waiting.'.format(**counts)
        ))
