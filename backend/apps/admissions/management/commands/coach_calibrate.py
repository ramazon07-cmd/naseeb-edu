"""Run the Naseeb AI calibration sets against a real model and report score, range and drift.

CALIBRATION ONLY COUNTS FOR THE MODEL IT RAN ON. A pass with `--provider claude_cli` (Sonnet, local
testing only) says nothing about the gateway model production uses: it does NOT unlock production scores
(ESSAY_COACH_SCORED_RUBRICS) while production runs a different model. Re-run with the production provider
and model before a rubric goes on that list.

Not part of any automatic run and never called by the tests (they mock the provider). Run it by hand
after every rubric, prompt or model change. It refuses to run without a real provider, because the
built-in rules reader says nothing about the model. For each text it makes N full checks, prints the
overall score of every run against the expected range and the drift, and checks grammar-fixed or
translated copies against their original. The exit code is non-zero when a text is out of range.
Real money is spent: each run is two paid calls.

The command always sees the levels and the overall, even for a rubric whose score students and counselors
do not see yet (ESSAY_COACH_SCORED_RUBRICS): passing this command is what puts a rubric on that list.
The letter set builds an unsaved letter and student (nothing is written to the database) and runs the
letter check's own spec.
"""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.admissions import ai_providers, letter_coach
from apps.admissions.essay_lab import calibration, coach
from apps.admissions.models import Essay, RecommendationLetter, StudentProfile


class Command(BaseCommand):
    help = 'Run the Naseeb AI calibration sets N times and report score vs expected range and drift (spends AI budget).'

    def add_arguments(self, parser):
        parser.add_argument('--runs', type=int, default=5, help='Runs per text (default 5).')
        parser.add_argument('--set', action='append', dest='sets', choices=calibration.SETS,
                            help='Only this set (repeatable). Default: all.')
        parser.add_argument('--text', action='append', dest='texts', help='Only this text id (repeatable).')
        parser.add_argument('--provider', choices=ai_providers.PROVIDERS, default=None,
                            help='Model provider (default: the AI_PROVIDER setting). claude_cli (local testing, '
                                 'development/test only) uses the Claude CLI; its scores count only for that '
                                 'model and never unlock production scores.')
        parser.add_argument('--report', help='Write a JSON report (provider, model, every score) to this path.')
        parser.add_argument('--list', action='store_true', help='List the texts and expected ranges; make no calls.')

    def handle(self, *args, **options):
        original = settings.AI_PROVIDER
        try:
            self.run_sets(options)
        finally:
            settings.AI_PROVIDER = original  # --provider is for this run only

    def run_sets(self, options):
        names = options['sets'] or list(calibration.SETS)
        selected = {}
        for name in names:
            run, cases = calibration.load_set(name)
            if options['texts']:
                cases = {case_id: case for case_id, case in cases.items() if case_id in options['texts']}
            selected[name] = (run, cases)
        if options['list']:
            for name, (run, cases) in selected.items():
                self.stdout.write(self.style.MIGRATE_HEADING(name))
                for case_id, case in cases.items():
                    params = calibration.case_params(name, run, case)
                    limit = params.get('word_limit', '-')
                    self.stdout.write(f"  {case_id}: overall {case.get('overall', '-')} limit {limit}")
            return
        if options['provider']:
            settings.AI_PROVIDER = options['provider']
        if ai_providers.uses_cli() and not ai_providers.cli_allowed():
            # The same rule the runtime uses: development/test, or production while the bridge is switched on.
            raise CommandError(
                '--provider claude_cli is only allowed when APP_ENV is development or test, '
                'or while AI_CLI_ALLOW_PRODUCTION is on.'
            )
        if not coach.gateway_configured():
            raise CommandError(
                'No real gateway configured (OUTBOUND_AI_ENABLED and AI_GATEWAY_API_KEY, or '
                'AI_PROVIDER=claude_cli with the claude binary on PATH, are required). '
                'The local reader cannot be calibrated.'
            )
        runs = max(1, options['runs'])
        provider = ai_providers.provider()
        model = ai_providers.active_model(settings.ESSAY_COACH_MODEL)
        model_label = settings.AI_TEST_CLI_MODEL if ai_providers.uses_cli() else model
        report = {'provider': provider, 'model': model, 'runs': runs, 'sets': {}}
        failures = 0
        for name, (run, cases) in selected.items():
            self.stdout.write(self.style.MIGRATE_HEADING(f'{name} (provider {provider}, model {model_label}, {runs} runs)'))
            means = {}
            problems = {}
            report['sets'][name] = {}
            for case_id, case in cases.items():
                params = calibration.case_params(name, run, case)
                if name == calibration.LETTER_SET:
                    results = self.collect_letter(params, case['text'], runs)
                else:
                    results = self.collect(params, case['text'], runs)
                means[case_id] = calibration.mean_scores(results)
                problems[case_id] = calibration.judge_case(case, results, runs)
                self.report(case_id, case, results, problems[case_id])
                report['sets'][name][case_id] = self.case_record(case, results)
            for case_id, case in cases.items():
                partner = case.get('same_as')
                if partner in means:
                    pair = calibration.judge_pair(case_id, partner, means[case_id], means[partner])
                    for problem in pair:
                        self.stdout.write(self.style.ERROR(f'  {case_id}: {problem}'))
                    problems[case_id] += pair
                    report['sets'][name][case_id]['problems'] = problems[case_id]
            for case_id in cases:
                report['sets'][name][case_id]['problems'] = problems[case_id]
            failures += sum(len(items) for items in problems.values())
        report['problems'] = failures
        if options['report']:
            Path(options['report']).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            self.stdout.write(f"Report written to {options['report']}")
        if failures:
            raise CommandError(f'Calibration failed: {failures} problem(s).')
        self.stdout.write(self.style.SUCCESS('Calibration passed.'))

    def collect(self, params, text, runs):
        essay = Essay(essay_type=params['essay_type'], prompt=params['prompt'], word_limit=params['word_limit'],
                      university_name=params['university_name'])
        results = []
        for _ in range(runs):
            try:
                results.append(coach.run_ai_check(essay, text, None, show_score=True)[0])
            except coach.CoachUnavailable:
                results.append(None)
        return results

    def collect_letter(self, params, text, runs):
        """Unsaved letter and student: the letter check's spec with the score shown."""
        person = params['student']
        user = get_user_model()(first_name=person.get('first_name', ''), last_name=person.get('last_name', ''))
        student = StudentProfile(user=user, application_profile={'gender': person.get('gender', '')})
        letter = RecommendationLetter(recommender_title=params['recommender_title'],
                                      relationship=params['relationship'], body=text)
        results = []
        for _ in range(runs):
            try:
                spec = letter_coach.build_spec(letter, student, text, show_score=True)
                results.append(coach.run_check(spec, None)[0])
            except coach.CoachUnavailable:
                results.append(None)
        return results

    def case_record(self, case, results):
        overalls = [item['overall'] if item and item.get('scored') else None for item in results]
        return {
            'expected': case.get('overall'), 'expect_safety': bool(case.get('expect_safety')),
            'expect_score_hidden': case.get('expect_score_hidden'), 'scores': overalls,
            'failed_runs': sum(1 for item in results if item is None), 'drift': calibration.drift(results),
            'results': [{key: item.get(key) for key in ('scored', 'overall', 'scores', 'safety', 'score_hidden')}
                        if item else None for item in results],
        }

    def report(self, case_id, case, results, problems):
        overalls = [item['overall'] if item and item.get('scored') else None for item in results]
        if 'overall' in case:
            expected = '{}-{}'.format(*case['overall'])
        else:
            expected = 'safety' if case.get('expect_safety') else f"hidden ({case.get('expect_score_hidden')})"
        line = (f"  {case_id}: score {overalls} expected {expected}, drift {calibration.drift(results)}"
                + ('  FAIL' if problems else '  ok'))
        self.stdout.write(self.style.ERROR(line) if problems else line)
        for problem in problems:
            self.stdout.write(f'    - {problem}')
