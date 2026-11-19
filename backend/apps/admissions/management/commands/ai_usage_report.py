import csv
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.admissions import ai_usage

COLUMNS = ('calls', 'paid_calls', 'ok_calls', 'error_rate', 'fallback_rate', 'budget_refused', 'local_fallback', 'estimated_calls')
TOKEN_PARTS = ('input_tokens', 'output_tokens', 'total_tokens')
STATS = ('sum', 'avg', 'p50', 'p90', 'max')


class Command(BaseCommand):
    help = 'Token usage per AI feature (or school, or day) for the financial model; counters only.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)
        parser.add_argument('--feature', choices=ai_usage.FEATURES)
        parser.add_argument('--by', choices=('feature', 'school', 'day'), default='feature')
        parser.add_argument('--csv', dest='csv_path')
        parser.add_argument('--price-input', type=Decimal, help='USD per 1M input tokens')
        parser.add_argument('--price-output', type=Decimal, help='USD per 1M output tokens')
        parser.add_argument('--purge-older-than', type=int, metavar='DAYS', help='delete rows older than DAYS and exit')

    def handle(self, *args, **options):
        if options['purge_older_than'] is not None:
            if options['purge_older_than'] < 1:
                raise CommandError('--purge-older-than must be at least 1 day.')
            deleted = ai_usage.purge(timezone.now() - timedelta(days=options['purge_older_than']))
            self.stdout.write(f'Deleted {deleted} rows older than {options["purge_older_than"]} days.')
            return
        if options['days'] < 1:
            raise CommandError('--days must be at least 1.')
        if (options['price_input'] is None) != (options['price_output'] is None):
            raise CommandError('Give both --price-input and --price-output, or neither.')
        data = ai_usage.summary(timezone.now() - timedelta(days=options['days']), options['feature'])
        rows = self.rows(data, options['by'])
        if options['price_input'] is None:
            # Fall back to the prices configured for the Health page (AI_PRICE_*_USD_PER_1M).
            configured = ai_usage.prices()
            if configured:
                options['price_input'], options['price_output'] = configured
        priced = options['price_input'] is not None
        header = ['group', *COLUMNS]
        header += [f'{part}_{stat}' for part in TOKEN_PARTS for stat in STATS]
        header += ['latency_p50_ms', 'latency_p95_ms', 'error_rate_pct']
        if priced:
            header += ['cost_usd', 'cost_per_paid_call_usd']
        table = []
        for name, row in rows:
            line = [name, *(row[column] for column in COLUMNS)]
            line += [row[part][stat] for part in TOKEN_PARTS for stat in STATS]
            line += [row['latency_ms']['p50'], row['latency_ms']['p95'], round(row['error_rate'] * 100, 2)]
            if priced:
                cost = (
                    Decimal(row['input_tokens']['sum']) * options['price_input']
                    + Decimal(row['output_tokens']['sum']) * options['price_output']
                ) / Decimal(1_000_000)
                line += [round(cost, 6), round(cost / row['paid_calls'], 6) if row['paid_calls'] else 0]
            table.append(line)
        if options['csv_path']:
            with open(options['csv_path'], 'w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(table)
            self.stdout.write(f'Wrote {len(table)} rows to {options["csv_path"]}.')
            return
        self.stdout.write('\t'.join(str(cell) for cell in header))
        for line in table:
            self.stdout.write('\t'.join(str(cell) for cell in line))

    @staticmethod
    def rows(data, by):
        if by == 'feature':
            return list(data['features'].items())
        key = 'school_id' if by == 'school' else 'day'
        return [(f'{row["feature"]}:{row[key]}', row) for row in data['schools' if by == 'school' else 'days']]
