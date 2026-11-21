from apps.admissions.telegram_import import importer
from core.jobs import ScheduledJobCommand


class Command(ScheduledJobCommand):
    help = (
        'Import new programs and scholarships from public Telegram channels. Production runs it '
        'hourly from 23:00 to 07:00 Tashkent through the bot (apps/telegram_bot/jobs.py); each run '
        'is incremental and time-boxed. Does nothing while OUTBOUND_AI_ENABLED is off.'
    )

    def run(self, **options):
        stats = importer.run()
        if stats.stopped in {'outbound_ai_off', 'gateway_not_configured', 'budget_off'}:
            self.stdout.write(self.style.WARNING(
                f'Telegram import skipped ({stats.stopped}): nothing was fetched or sent and no program was added.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'Telegram import: {stats.summary()}'))
        return stats.added
