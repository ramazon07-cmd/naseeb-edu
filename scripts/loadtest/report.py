"""Merge Locust stats and per-request cost into one table per endpoint.

    python scripts/loadtest/report.py RESULTS_DIR [BASELINE_DIR]

RESULTS_DIR holds ``run_stats.csv`` (``locust --csv RESULTS_DIR/run``) and
``cost.csv`` (written by the locustfile). With BASELINE_DIR, p95 and query
counts are shown as ``before -> after``.
"""
import csv
import sys
from pathlib import Path


def load(directory):
    directory = Path(directory)
    rows = {}
    with open(directory / 'run_stats.csv', newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            key = f"{row['Type']} {row['Name']}".strip()
            rows[key] = {'stats': row}
    cost_file = directory / 'cost.csv'
    if cost_file.exists():
        with open(cost_file, newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                rows.setdefault(row['endpoint'], {})['cost'] = row
    return rows


def cell(row, section, field, default='-'):
    return (row.get(section) or {}).get(field, default)


def main():
    current = load(sys.argv[1])
    baseline = load(sys.argv[2]) if len(sys.argv) > 2 else {}
    header = ['endpoint', 'reqs', 'fail', 'rps', 'p50', 'p95', 'p99', 'queries', 'db ms', 'cpu ms', 'KB']
    print('| ' + ' | '.join(header) + ' |')
    print('|' + '---|' * len(header))
    for key in sorted(current, key=lambda name: (name == 'Aggregated', name.split(' ', 1)[-1])):
        row, old = current[key], baseline.get(key, {})

        def pair(section, field):
            value = cell(row, section, field)
            if old:
                return f"{cell(old, section, field)} → {value}"
            return value

        print('| ' + ' | '.join([
            key, cell(row, 'stats', 'Request Count'), cell(row, 'stats', 'Failure Count'),
            f"{float(cell(row, 'stats', 'Requests/s', 0) or 0):.2f}", cell(row, 'stats', '50%'),
            pair('stats', '95%'), cell(row, 'stats', '99%'), pair('cost', 'avg_queries'),
            cell(row, 'cost', 'avg_db_ms'), pair('cost', 'avg_cpu_ms'), cell(row, 'cost', 'avg_kb'),
        ]) + ' |')


if __name__ == '__main__':
    main()
