from apps.admissions.telegram_import import importer
from core.jobs import ScheduledJobCommand


# Stops that are the provider's or the network's fault, not an expected idle run: the job is recorded as failed
# (and its reason kept), so the health page and the bot show it instead of a green "ok" that did nothing.
OUTAGE_STOPS = {'gateway_unavailable', 'gateway_not_configured'}


class ImportOutage(Exception):
    """The import could not do its work (provider down or not set up, every channel unreadable)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.job_reason = reason


class Command(ScheduledJobCommand):
    help = (
        'Import new programs and scholarships from public Telegram channels. Production runs it '
        'hourly from 23:00 to 07:00 Tashkent through the bot (apps/telegram_bot/jobs.py); each run '
        'is incremental and time-boxed. Does nothing while OUTBOUND_AI_ENABLED is off.'
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--time-budget', type=int, default=None,
            help='Seconds this run may start new work (default TELEGRAM_IMPORT_TIME_BUDGET_SECONDS).',
        )

    def run(self, **options):
        stats = importer.run(time_budget=options.get('time_budget'))
        outage = stats.stopped if stats.stopped in OUTAGE_STOPS else (
            'channels_unreadable' if stats.failed_channels and not stats.fetched else '')
        if outage:
            self.stdout.write(self.style.ERROR(f'Telegram import failed ({outage}): {stats.summary()}'))
            raise ImportOutage(outage)
        if stats.stopped in {'outbound_ai_off', 'gateway_not_configured', 'budget_off'}:
            self.stdout.write(self.style.WARNING(
                f'Telegram import skipped ({stats.stopped}): nothing was fetched or sent and no program was added.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'Telegram import: {stats.summary()}'))
        return stats.added
