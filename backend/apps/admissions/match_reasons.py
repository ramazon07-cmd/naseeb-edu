"""The optional "Why these fit you" lines of the college match: one AI call, one line per card.

The default match makes no AI call. This runs only when the student asks, writes one short line for each
of the (up to 10) cards, and counts as one unit against the daily limit. The model sees the card facts (band,
subject rank, SAT range and score, admit rate, cost against budget, aid) and the student's stated majors,
academics score and budget only: never essay or letter text, activities, or the student's name (free-text
fields still go through the same redaction as the letter coach).

Number check: a line may only use numbers that appear in its own card (never the card's internal id) or in the
student facts. A line with any other number (a made-up admit rate, a wrong rank) is replaced by an empty line,
which the page does not show. So is a line that talks about the student's chance or probability of admission:
only the university's own admit rate may be quoted, never a personal prediction.

The answer is cached by an input hash of the card list and the profile version, so asking again for the
same list costs nothing. A failed call gives its unit back and answers 503.
"""
import hashlib
import json
import re
import time
import urllib.error

from django.conf import settings

from apps.users.cache_safety import cache_get, cache_set

from . import ai_budget, ai_providers, ai_usage
from .assistant import redact_pii
from .streaming import release_db_connection
from .essay_lab import coach
from .letter_coach import anonymize

FEATURE = 'college_match_reasons'
VERSION = 'reasons-v3'
CACHE_SECONDS = 7 * 24 * 60 * 60
LANGUAGES = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}
MAX_LINE_CHARS = 240
MAX_TOKENS = 1400
NUMBER = re.compile(r'\d[\d,.]*')
# A personal admission prediction (English, Russian, Uzbek): a chance/odds/probability word together with an
# admission word and a second-person word (you/your, ваш, sizning), or a flat "you will be admitted". The model may quote the university's admit rate, and words such
# as "opportunities" (imkoniyatlar) or a probability-and-statistics program are fine on their own.
CHANCE_WORD = re.compile(
    r'chances?\b|odds\b|probabilit|likelihood|\bshans\w*|шанс|вероятн|ehtimol|imkoniyat(?!lar)',
    re.IGNORECASE,
)
ADMISSION_WORD = re.compile(
    r'admi(?:t|ssion|tted)|accept|get(?:ting)? in\b|enrol|поступ|принят|зачисл|qabul|kirish|o.qishga',
    re.IGNORECASE,
)
PREDICTION = re.compile(r'\byou (?:will|would|should) (?:likely |easily |surely )?(?:be )?(?:admitted|accepted|get in)', re.IGNORECASE)


PERSONAL = re.compile(
    r"\byou(?:r|rs|'re|'ll)?\b|\bваш\w*|\bвы\b|\bвас\b|\bтеб\w*|\bsizning\b|\bsiz\w*|\bsening\b|\bsen\b",
    re.IGNORECASE,
)


def predicts_admission(line):
    """Whether a line predicts the student's OWN admission: a chance/odds/probability of admission said about
    "you", or a flat "you will be admitted". A grounded admit or acceptance rate of the university is fine."""
    personal_chance = CHANCE_WORD.search(line) and ADMISSION_WORD.search(line) and PERSONAL.search(line)
    return bool(personal_chance or PREDICTION.search(line))


SYSTEM = """You write short "why this fits you" lines for a student's list of universities.
For each university card write exactly one plain sentence of at most 25 words, using only the facts given for
that card: its band, the student's academics score and budget, and the university's facts. Use only numbers that
appear in that card or the student facts; when admit_rate_estimated is true, call the admit rate an estimate.
Be honest: if the band is far reach or reach, say it is ambitious and why it is still worth considering; never
promise admission.
Never mention essays, recommendation letters, grammar, English fluency or the student's name.
Write in {language}. Return one JSON object and nothing else:
{{"reasons": {{"<university id>": "<one sentence>"}}}} with one entry for every card id."""


class ReasonsUnavailable(Exception):
    """The lines could not be produced; ``code`` and ``status`` tell the view what to answer."""

    def __init__(self, code, status=503):
        super().__init__(code)
        self.code, self.status = code, status


def cards(data, profile):
    """The card facts the model may see: public university facts plus the rule-based band and chance notes."""
    def clean(text):
        return redact_pii(anonymize(text, profile))

    out = []
    for group in data['groups']:
        for row in group['results']:
            fit = row['fit']
            subject = row.get('subject') or {}
            sat = row['sat']
            out.append({
                'id': row['id'], 'name': row['name'], 'country': row['country'], 'band': row['band'],
                'qs_rank': row.get('ranking'), 'subject': subject.get('name'),
                'subject_rank_qs_2026': None if subject.get('overall') else subject.get('rank_label'),
                'sat_position': sat['position'],
                'act_score' if sat['position'] == 'act_used' else 'sat_score': sat.get('score'),
                'sat_range_min': sat.get('min'), 'sat_range_max': sat.get('max'),
                'aid_for_internationals': row['aid_status'],
                'admit_rate': fit['chance'].get('admit_rate'),
                'admit_rate_estimated': fit['chance'].get('admit_rate_estimated'),
                'cost_usd': row.get('cost_usd'), 'cost_vs_budget': row.get('cost_vs_budget'),
                'offers_international_aid': row.get('offers_international_aid'),
                'max_aid_award_usd_per_year': (row.get('aid') or {}).get('max_award_usd'),
                'min_student_pays_usd_per_year': (row.get('aid') or {}).get('min_student_pays_usd'),
                'programs': [program['name'] for program in row.get('suggested_programs', [])],
                'strengths': [clean(item['text']) for item in fit['reasons'][:2]],
                'watch_outs': [clean(item['text']) for item in fit['gaps'][:2]],
            })
    return out


def profile_facts(profile, rubric):
    """The stated majors, the academics score and the budget; free text is anonymized and redacted like the
    letter coach does. Activities and essays are not used by the match, so the model does not see them."""
    majors = redact_pii(anonymize(profile.target_major, profile))[:160]
    return {
        'intended_majors': majors, 'scores_out_of_10': {'academics': rubric.get('academics')},
        'budget_usd': profile.budget_usd,
    }


def input_hash(version_key, items, language):
    """Everything the lines depend on: the card list, the profile version (fit key), language, prompt and model."""
    payload = json.dumps(
        {'v': VERSION, 'model': coach.current_model(), 'profile': version_key, 'language': language,
         'cards': [(item['id'], item['band']) for item in items]}, sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def numbers(text):
    """The numbers in ``text`` as values: commas removed, trailing dots stripped ("25,000." is 25000, "12" is 12.0)."""
    found = set()
    for token in NUMBER.findall(text):
        token = token.replace(',', '').rstrip('.')
        try:
            found.add(float(token))
        except ValueError:
            found.add(token)
    return found


def validate(raw, items, student):
    """``{card id: line}``. A missing or empty line raises; a line naming a number that is in neither its card
    (its id does not count) nor the student facts, or one that states an admission chance, becomes an empty
    line (not shown)."""
    reasons = raw.get('reasons') if isinstance(raw, dict) else None
    if not isinstance(reasons, dict):
        raise ValueError('reasons must be an object')
    known = numbers(json.dumps(student, ensure_ascii=False))
    lines = {}
    for item in items:
        line = reasons.get(str(item['id']))
        if not isinstance(line, str) or not line.strip():
            raise ValueError('a card has no line')
        line = line.strip()[:MAX_LINE_CHARS]
        facts = {key: value for key, value in item.items() if key != 'id'}  # an id is a label, not a fact
        allowed = known | numbers(json.dumps(facts, ensure_ascii=False))
        lines[str(item['id'])] = line if numbers(line) <= allowed and not predicts_admission(line) else ''
    return lines


def request_lines(student, items, language):
    messages = [
        {'role': 'system', 'content': SYSTEM.format(language=LANGUAGES[language])},
        {'role': 'user', 'content': json.dumps({'student': student, 'cards': items}, ensure_ascii=False)},
    ]
    deadline = time.monotonic() + settings.ESSAY_COACH_TOTAL_SECONDS
    return coach._request_gateway(messages, MAX_TOKENS, deadline, ('reasons',))


def generate(profile, user, data, version_key, rubric, language='en'):
    """``({card id: line}, cached)`` for the match ``data``; raises ReasonsUnavailable (503) when it cannot."""
    language = language if language in LANGUAGES else 'en'
    items = cards(data, profile)
    if not items:
        return {}, True
    key = f'college-match-reasons:{profile.pk}:{input_hash(version_key, items, language)}'
    cached = cache_get(key)
    if cached is not None:
        return cached, True
    if not coach.gateway_configured():
        raise ReasonsUnavailable('coach_unavailable')
    reservation = ai_budget.consume(FEATURE, user)
    if not reservation:
        ai_usage.record(FEATURE, user, provider=ai_providers.provider(), status=ai_usage.BUDGET_REFUSED)
        raise ReasonsUnavailable('coach_resting')
    sink = ai_usage.begin()
    try:
        student = profile_facts(profile, rubric)
        release_db_connection()  # don't hold a pooled connection while the provider works
        lines = validate(request_lines(student, items, language), items, student)
    except (KeyError, IndexError, TypeError, ValueError, urllib.error.URLError, TimeoutError, OSError):
        ai_usage.record(
            FEATURE, user, provider=ai_providers.provider(), status=ai_usage.FAILED,
            sink=sink, refunded=not sink.get('answered'),
        )
        coach.logger.warning('%s_provider_failure user_id=%s', FEATURE, getattr(user, 'pk', None))
        ai_budget.refund(reservation)  # a failed call is free
        raise ReasonsUnavailable('coach_unavailable')
    ai_usage.record(FEATURE, user, provider=ai_providers.provider(), status=ai_usage.OK)
    cache_set(key, lines, CACHE_SECONDS)
    return lines, False
