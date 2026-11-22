"""Calibration sets for Naseeb AI scoring: loading them and judging results against expected ranges.

A set is a folder in `rubrics/calibration/<rubric>/` with `<id>.txt` texts and `expected.json`:

    {"run": {"prompt": "", "word_limit": 200, "university_name": ""},   # defaults for every case of the set
     "cases": {"<id>": {"levels": {"<api key>": [min, max]}, "overall": [min, max],
                        "prompt": ..., "word_limit": ..., "essay_type": ...,      # optional overrides
                        "university_name": ...,
                        "adversarial": true, "not_safety": true,                   # optional checks
                        "same_as": "<id>", "forbid_in_notes": ["<regex>"],
                        "expect_safety": true,                 # every run must be routed to current danger
                        "expect_score_hidden": "short",        # every run must hide its score this way
                        "expect_sensitive": ["health"], "min_reader_notes": 1}}}   # letters only

The letter set's run and cases may also give "recommender_title", "relationship" and "student"
({"first_name", "last_name", "gender"}). Level keys are the API's keys (the supplement rubric's evidence is
`specificity`, its concision is `structure`). Level ranges are the documented level ±1, and the overall
range is the gate; every overall range lies inside what its level ranges can reach. Nothing here calls the
gateway: `manage.py coach_calibrate` does, and only when it is run.
"""

import json
import re
from pathlib import Path

from . import coach

CALIBRATION_DIR = Path(__file__).parent / 'rubrics' / 'calibration'
# Set names are the rubric names.
SETS = ('personal_statement', 'supplement', 'recommendation_letter')
LETTER_SET = 'recommendation_letter'
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
    """What a case is run with: essay type, prompt, word limit and target school (essays), or the
    recommender title, relationship and student (letters)."""
    if name == LETTER_SET:
        return {
            'recommender_title': case.get('recommender_title', run.get('recommender_title', '')),
            'relationship': case.get('relationship', run.get('relationship', '')),
            'student': {**run.get('student', {}), **case.get('student', {})},
        }
    return {
        'essay_type': case.get('essay_type', name),
        'prompt': case.get('prompt', run.get('prompt', '')),
        'word_limit': case.get('word_limit', run.get('word_limit')),
        'university_name': case.get('university_name', run.get('university_name', '')),
    }


def reachable(rubric, levels):
    """(lowest, highest) overall the level ranges allow; a criterion with no range may be 1-4."""
    keys = list(coach.CRITERIA[rubric])
    lows = {key: levels.get(key, [1, 4])[0] for key in keys}
    highs = {key: levels.get(key, [1, 4])[1] for key in keys}
    return coach.compute_overall(rubric, lows), coach.compute_overall(rubric, highs)


def note_texts(result):
    """The text of every note and reader note a result shows."""
    notes = [*(result.get('notes') or []), *(result.get('reader_notes') or [])]
    return [f"{note.get('question', '')} {note.get('context', '')}" for note in notes]


def judge_case(case, results, runs):
    """Problems of one case: a list of strings, empty when the case passes.

    `results` holds one v2 result per run, or None for a run that failed. A scored result is needed for
    every run; a safety message or an unscored one counts as unusable.
    """
    problems = []
    if case.get('expect_safety'):
        missed = sum(1 for item in results if not (item and item.get('safety') in ('current_danger', True)))
        return [f'{missed} of {runs} runs not routed to the safety message'] if missed else []
    if case.get('expect_score_hidden'):
        wanted = case['expect_score_hidden']
        missed = sum(1 for item in results if not (item and item.get('score_hidden') == wanted and not item.get('scored')))
        return [f'{missed} of {runs} runs did not hide the score as {wanted}'] if missed else []
    usable = [item for item in results if item and item.get('scored')]
    if any(item and item.get('safety') in ('current_danger', True) for item in results) and case.get('not_safety'):
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
    for kind in case.get('expect_sensitive', []):
        if any(kind not in [entry.get('kind') for entry in item.get('sensitive') or []] for item in usable):
            problems.append(f'a run has no {kind} sensitive note')
    if 'min_reader_notes' in case and any(len(item.get('reader_notes') or []) < case['min_reader_notes'] for item in usable):
        problems.append(f"a run has fewer than {case['min_reader_notes']} reader notes")
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
