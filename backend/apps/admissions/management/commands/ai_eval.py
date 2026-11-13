import json

from django.core.management.base import BaseCommand, CommandError

from apps.admissions import ai_eval


class Command(BaseCommand):
    help = (
        'Offline evaluation of the AI features\' validation layers on fixed sample inputs (no provider call). '
        'Exits non-zero when a case fails. --live also calls the real provider, only when explicitly asked and configured.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--feature', choices=('assistant', 'education_match', 'recommendation_letter'))
        parser.add_argument('--live', action='store_true', help='also run a few real provider calls (costs tokens; needs OUTBOUND_AI_ENABLED and keys)')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        results = ai_eval.run(live=options['live'], feature=options['feature'])
        failed = [row for row in results if row.passed is False]
        if options['as_json']:
            self.stdout.write(json.dumps([row._asdict() for row in results], indent=2))
        else:
            for row in results:
                mark = 'SKIP' if row.passed is None else 'PASS' if row.passed else 'FAIL'
                self.stdout.write(f'{mark}\t{row.feature}\t{row.name}\t{row.detail}'.rstrip())
            passed = sum(1 for row in results if row.passed)
            self.stdout.write(f'{passed} passed, {len(failed)} failed, {len(results) - passed - len(failed)} skipped')
        if failed:
            raise CommandError(f'{len(failed)} AI eval case(s) failed.')
