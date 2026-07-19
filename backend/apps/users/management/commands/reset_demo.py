from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Reset local demo database content and recreate working Naseeb Edu demo data.'

    def handle(self, *args, **options):
        if not settings.DEMO_ACCOUNTS_ENABLED:
            raise CommandError('Demo accounts are disabled in this environment.')

        self.stdout.write('Resetting local demo data...')
        call_command('flush', interactive=False, verbosity=0)
        call_command('seed_demo')
        self.stdout.write(self.style.SUCCESS('Demo reset done. Use the configured local demo credentials.'))
