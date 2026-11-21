"""Calibration sets for Naseeb AI scoring: loading them and judging results against expected ranges.

A set is a folder in `rubrics/calibration/<essay type>/` with `<id>.txt` texts and `expected.json`:

    {"run": {"prompt": "", "word_limit": 200},          # defaults for every case of the set
     "cases": {"<id>": {"levels": {"<api key>": [min, max]}, "overall": [min, max],
                        "prompt": ..., "word_limit": ..., "essay_type": ...,      # optional overrides
                        "adversarial": true, "not_safety": true,                   # optional checks
                        "same_as": "<id>", "forbid_in_notes": ["<regex>"]}}}

Level keys are the API's keys (the supplement rubric's evidence is `specificity`, its concision is
`structure`). Nothing here calls the gateway: `manage.py coach_calibrate` does, and only when it is run.
"""

import json
import re
from pathlib import Path

CALIBRATION_DIR = Path(__file__).parent / 'rubrics' / 'calibration'
SETS = ('personal_statement', 'supplement')
# At most this many levels between the lowest and highest score of one criterion over the runs.
MAX_DRIFT = 1
# A text that must come out the same however it is written (grammar fixed, translated) may differ by this much.
PAIR_TOLERANCE = 1
ADVERSARIAL_MAX_LEVEL = 3


def load_set(name):
    """-> (run defaults, {case id: case}) with each case's `text` read from its file."""
    folder = CALIBRATION_DIR / name
    data = json.loads((folder / 'expected.json').read_text(encoding='utf-8'))
    cases = {}
    for case_id, case in data['cases'].items():
        cases[case_id] = {**case, 'text': (folder / f'{case_id}.txt').read_text(encoding='utf-8')}
    return data['run'], cases


def case_params(name, run, case):
    """The essay type, prompt and word limit a case is run with."""
    return {
        'essay_type': case.get('essay_type', name),
        'prompt': case.get('prompt', run.get('prompt', '')),
        'word_limit': case.get('word_limit', run.get('word_limit')),
    }


def note_texts(result):
    return [f"{note.get('question', '')} {note.get('context', '')}" for note in result.get('notes') or []]


def judge_case(case, results, runs):
    """Problems of one case: a list of strings, empty when the case passes.

    `results` holds one v2 result per run, or None for a run that failed. A scored result is needed for
    every run; a safety message or an unscored one counts as unusable.
    """
    problems = []
    usable = [item for item in results if item and item.get('scored')]
    if any(item and item.get('safety') == 'current_danger' for item in results) and case.get('not_safety'):
        problems.append('routed to the safety message')
    if len(usable) < runs:
        problems.append(f'{runs - len(usable)} of {runs} runs unusable')
    if not usable:
        return problems
    low, high = case['overall']
    overalls = [item['overall'] for item in usable]
    if any(not low <= value <= high for value in overalls):
        problems.append(f'overall out of range {low}-{high}: {sorted(overalls)}')
    for key, (low, high) in case.get('levels', {}).items():
        values = [item['scores'][key] for item in usable]
        if any(not low <= value <= high for value in values):
            problems.append(f'{key} out of range {low}-{high}: {sorted(values)}')
    for key in usable[0]['scores']:
        values = [item['scores'][key] for item in usable]
        if max(values) - min(values) > MAX_DRIFT:
            problems.append(f'{key} drift {max(values) - min(values)} over {len(values)} runs: {sorted(values)}')
        if case.get('adversarial') and max(values) > ADVERSARIAL_MAX_LEVEL:
            problems.append(f'adversarial text scored {max(values)} on {key}')
    for pattern in case.get('forbid_in_notes', []):
        regex = re.compile(pattern, re.IGNORECASE)
        if any(regex.search(text) for item in usable for text in note_texts(item)):
            problems.append(f'a note matches the forbidden pattern {pattern}')
    return problems


def mean_scores(results):
    """{key: mean level over the usable runs} or None."""
    usable = [item for item in results if item and item.get('scored')]
    if not usable:
        return None
    return {key: sum(item['scores'][key] for item in usable) / len(usable) for key in usable[0]['scores']}


def judge_pair(name, partner_name, means, partner_means):
    """Problems when a text and its grammar-fixed or translated copy differ by more than PAIR_TOLERANCE."""
    if not means or not partner_means:
        return []
    return [
        f'{key} differs from {partner_name} by {abs(means[key] - partner_means[key]):.1f} levels'
        for key in means
        if key in partner_means and abs(means[key] - partner_means[key]) > PAIR_TOLERANCE
    ]


def drift(results, key=None):
    values = [item['overall'] if key is None else item['scores'][key] for item in results if item and item.get('scored')]
    return max(values) - min(values) if values else 0
