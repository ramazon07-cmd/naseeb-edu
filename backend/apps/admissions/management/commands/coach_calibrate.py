"""Run the Essay Coach calibration sets against the real gateway and report range hits and drift.

Needs a configured gateway (outbound AI on and AI_GATEWAY_API_KEY set); otherwise it refuses,
because the local heuristic reader says nothing about the model. Gate (rubrics/README.md):
every score inside its expected range, at most one level of drift over N runs at temperature 0,
adversarial texts at most 3 on every criterion, and unchanged scores after a whitespace change.
Run it on every rubric, prompt or model change; the exit code is non-zero when the gate fails.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.admissions.essay_lab import coach
from apps.admissions.models import Essay

CALIBRATION = Path(coach.__file__).parent / 'rubrics' / 'calibration'
# Run parameters the expected ranges assume (calibration/README.md).
RUN_PARAMS = {
    'personal_statement': {'prompt': '', 'word_limit': 200},
    'supplement': {'prompt': 'Why do you want to study computer science at Eastfield University?', 'word_limit': 150},
    'scholarship': {
        'prompt': 'Describe your goals and how this scholarship, which supports students who will bring skills '
                  'back to rural communities, would help you.',
        'word_limit': 150,
    },
    'free_writing': {'prompt': '', 'word_limit': None},
}
MAX_DRIFT = 1
ADVERSARIAL_MAX = 3


class Command(BaseCommand):
    help = 'Run the Essay Coach calibration set N times at temperature 0 and report range hits and drift.'

    def add_arguments(self, parser):
        parser.add_argument('--runs', type=int, default=5, help='Runs per text (default 5).')
        parser.add_argument('--type', action='append', dest='types', choices=sorted(coach.CRITERIA),
                            help='Only this essay type (repeatable). Default: all.')

    def handle(self, *args, **options):
        if not coach.gateway_configured():
            raise CommandError(
                'No real gateway configured (OUTBOUND_AI_ENABLED and AI_GATEWAY_API_KEY are required). '
                'The local reader cannot be calibrated.'
            )
        runs = max(1, options['runs'])
        failures = 0
        for essay_type in options['types'] or sorted(coach.CRITERIA):
            expected = json.loads((CALIBRATION / essay_type / 'expected.json').read_text(encoding='utf-8'))
            self.stdout.write(self.style.MIGRATE_HEADING(f'{essay_type} (model {coach.settings.ESSAY_COACH_MODEL})'))
            for case_id, ranges in expected.items():
                text = (CALIBRATION / essay_type / f'{case_id}.txt').read_text(encoding='utf-8')
                failures += self.run_case(essay_type, case_id, text, ranges, runs)
        if failures:
            raise CommandError(f'Calibration gate failed: {failures} problem(s).')
        self.stdout.write(self.style.SUCCESS('Calibration gate passed.'))

    def collect(self, essay_type, text, runs):
        params = RUN_PARAMS[essay_type]
        essay = Essay(essay_type=essay_type, prompt=params['prompt'], word_limit=params['word_limit'])
        results = []
        for _ in range(runs):
            try:
                result, _model = coach.run_ai_check(essay, text, use_cache=False)
            except coach.CoachUnavailable:
                results.append(None)
                continue
            results.append(result if result['mode'] == coach.MODE_CHECK else None)
        return results

    def run_case(self, essay_type, case_id, text, ranges, runs):
        problems = []
        results = [item for item in self.collect(essay_type, text, runs) if item]
        if len(results) < runs:
            problems.append(f'{runs - len(results)} of {runs} runs unusable')
        keys = list(coach.CRITERIA[essay_type])
        hits = total = 0
        for key in (*keys, 'overall'):
            values = [item['overall'] if key == 'overall' else item['scores'][key] for item in results]
            if not values:
                continue
            low, high = ranges[key]
            inside = sum(low <= value <= high for value in values)
            hits += inside
            total += len(values)
            drift = max(values) - min(values)
            if inside < len(values):
                problems.append(f'{key} out of range {low}-{high}: {sorted(values)}')
            if key != 'overall' and drift > MAX_DRIFT:
                problems.append(f'{key} drift {drift} over {runs} runs: {sorted(values)}')
            if case_id.startswith('adv_') and key != 'overall' and max(values) > ADVERSARIAL_MAX:
                problems.append(f'adversarial text scored {max(values)} on {key}')
        # Whitespace-only change must not change scores (compared with the first run).
        if results:
            spaced = '\n'.join(line.replace(' ', '  ') for line in text.replace('\n', '\r\n').split('\r\n'))
            changed = [item for item in self.collect(essay_type, spaced, 1) if item]
            if changed:
                base = results[0]['scores']
                moved = {key: (base[key], changed[0]['scores'][key]) for key in keys
                         if abs(base[key] - changed[0]['scores'][key]) > 0}
                if moved:
                    problems.append(f'whitespace change moved scores {moved}')
        rate = f'{hits}/{total}' if total else '0/0'
        line = f'  {case_id}: in range {rate}' + ('' if not problems else '  FAIL')
        self.stdout.write(self.style.ERROR(line) if problems else line)
        for problem in problems:
            self.stdout.write(f'    - {problem}')
        return len(problems)
