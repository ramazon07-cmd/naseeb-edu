"""The optional "Why these fit you" lines of the college match: one AI call, one line per card.

The default match makes no AI call. This runs only when the student asks, writes one short line for each
of the (up to 12) cards, and counts as one unit against the daily limit. The model sees the band, the
student's factor numbers and university facts only: never essay or letter text, never the student's name
(free-text fields still go through the same redaction as the letter coach).

The answer is cached by an input hash of the card list and the profile version, so asking again for the
same list costs nothing. A failed call gives its unit back and answers 503.
"""
import hashlib
import json
import time
import urllib.error

from django.conf import settings

from apps.users.cache_safety import cache_get, cache_set

from . import ai_budget, ai_usage
from .assistant import redact_pii
from .essay_lab import coach
from .letter_coach import anonymize

FEATURE = 'college_match_reasons'
VERSION = 'reasons-v1'
CACHE_SECONDS = 7 * 24 * 60 * 60
LANGUAGES = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}
MAX_LINE_CHARS = 240
MAX_TOKENS = 1400

SYSTEM = """You write short "why this fits you" lines for a student's list of universities.
For each university card write exactly one plain sentence of at most 25 words, using only the facts given for
that card: its band, the student's factor numbers, and the university's facts. Be honest: if the band is far
reach or reach, say it is ambitious and why it is still worth considering; never promise admission.
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
            out.append({
                'id': row['id'], 'name': row['name'], 'country': row['country'], 'band': row['band'],
                'qs_rank': row.get('ranking'), 'subject': subject.get('name'),
                'subject_rank_qs_2026': None if subject.get('overall') else subject.get('rank_label'),
                'sat_position': row['sat']['position'], 'aid_for_internationals': row['aid_status'],
                'admit_rate': fit['chance'].get('admit_rate'),
                'fit_score': fit['match_score'], 'cost_usd': row.get('cost_usd'),
                'offers_international_aid': row.get('offers_international_aid'),
                'programs': [program['name'] for program in row.get('suggested_programs', [])],
                'strengths': [clean(item['text']) for item in fit['reasons'][:2]],
                'watch_outs': [clean(item['text']) for item in fit['gaps'][:2]],
            })
    return out


def profile_facts(profile, rubric):
    """Factor numbers and the stated majors; free text is anonymized and redacted like the letter coach does."""
    majors = redact_pii(anonymize(profile.target_major, profile))[:160]
    return {'intended_majors': majors, 'scores_out_of_10': {key: value for key, value in rubric.items() if value is not None}}


def input_hash(version_key, items, language):
    """Everything the lines depend on: the card list, the profile version (fit key), language, prompt and model."""
    payload = json.dumps(
        {'v': VERSION, 'model': coach.current_model(), 'profile': version_key, 'language': language,
         'cards': [(item['id'], item['band']) for item in items]}, sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def validate(raw, ids):
    reasons = raw.get('reasons') if isinstance(raw, dict) else None
    if not isinstance(reasons, dict):
        raise ValueError('reasons must be an object')
    lines = {}
    for card_id in ids:
        line = reasons.get(str(card_id))
        if not isinstance(line, str) or not line.strip():
            raise ValueError('a card has no line')
        lines[str(card_id)] = line.strip()[:MAX_LINE_CHARS]
    return lines


def request_lines(profile, rubric, items, language):
    messages = [
        {'role': 'system', 'content': SYSTEM.format(language=LANGUAGES[language])},
        {'role': 'user', 'content': json.dumps(
            {'student': profile_facts(profile, rubric), 'cards': items}, ensure_ascii=False)},
    ]
    deadline = time.monotonic() + settings.ESSAY_COACH_TOTAL_SECONDS
    return coach._request_gateway(messages, MAX_TOKENS, deadline)


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
    if not ai_budget.consume(FEATURE, user):
        ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.BUDGET_REFUSED)
        raise ReasonsUnavailable('coach_resting')
    ai_usage.begin()
    try:
        lines = validate(request_lines(profile, rubric, items, language), [item['id'] for item in items])
    except (KeyError, IndexError, TypeError, ValueError, urllib.error.URLError, TimeoutError, OSError):
        ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.FAILED)
        coach.logger.warning('%s_provider_failure user_id=%s', FEATURE, getattr(user, 'pk', None))
        ai_budget.refund(FEATURE, user)  # a failed call is free
        raise ReasonsUnavailable('coach_unavailable')
    ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.OK)
    cache_set(key, lines, CACHE_SECONDS)
    return lines, False
