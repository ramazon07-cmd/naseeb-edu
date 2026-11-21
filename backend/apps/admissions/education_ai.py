"""De-identified AI explanations for assessment-ranked major matches.

Goes through the same Vercel AI Gateway, daily budget and usage log as the
other AI features. Nothing identifying is sent: no name, email, username,
school or id, only assessment scores and versions, grade and test scores,
and the major and subject names the student picked.
"""

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from core.ai_policy import outbound_ai_allowed
from apps.users.cache_safety import cache_get, cache_set

from . import ai_budget, ai_usage


logger = logging.getLogger('naseeb.education_ai')
MAX_TEXT_LENGTH = 500
CURRENT_ASSESSMENTS = {'personality', 'interests', 'subjects', 'reasoning'}
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_OUTPUT_TOKENS = 1200
PROMPT_VERSION = 1
FEATURE = 'education_match'


class EducationAIUnavailable(Exception):
    """AI is switched off, not configured, or the provider failed."""


class EducationAIBudgetExhausted(Exception):
    """A daily cap (platform, school or user) is reached."""


def recommendation_ai_available():
    return outbound_ai_allowed() and bool(settings.AI_GATEWAY_API_KEY)


def latest_assessment_scores(profile):
    latest = {}
    attempts = profile.challenge_attempts.order_by('-completed_at', '-id')
    for attempt in attempts:
        if attempt.challenge in CURRENT_ASSESSMENTS and attempt.challenge not in latest:
            latest[attempt.challenge] = {
                'instrument_version': attempt.instrument_version,
                'scores': attempt.scores,
            }
    return latest


def _safe_text(value, default=''):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:MAX_TEXT_LENGTH] or default


def _validate_result(result, major_candidates, subject_strengths):
    allowed_majors = {major.casefold(): major for major in major_candidates}
    allowed_subjects = {subject.casefold(): subject for subject in subject_strengths}
    major_guidance = []
    for item in result.get('major_guidance', []):
        if not isinstance(item, dict):
            continue
        major = allowed_majors.get(str(item.get('major', '')).casefold())
        if not major:
            continue
        subjects = []
        for subject in item.get('subjects_to_focus', []):
            matched = allowed_subjects.get(str(subject).casefold())
            if matched and matched not in subjects:
                subjects.append(matched)
        major_guidance.append({
            'major': major,
            'why_fit': _safe_text(item.get('why_fit'), 'This major aligns with your assessment profile.'),
            'subjects_to_focus': subjects[:4],
            'explore_next': _safe_text(item.get('explore_next'), f'Explore an introductory {major} project.'),
        })
    questions = [_safe_text(question) for question in result.get('questions_to_consider', []) if _safe_text(question)][:4]
    return {
        'mode': 'ai',
        'summary': _safe_text(result.get('summary'), 'Your assessment-based education guidance is ready.'),
        'major_guidance': major_guidance,
        'questions_to_consider': questions,
        'disclaimer': 'AI guidance is advisory and does not predict admission or define what you can study.',
    }


SYSTEM_PROMPT = """You are an education exploration assistant for secondary-school students.
Return only a JSON object with: summary, major_guidance, questions_to_consider.
major_guidance items require major, why_fit, subjects_to_focus, explore_next.
Use only candidate majors and subjects supplied in the input. Never invent a program requirement,
ranking, cost, deadline, scholarship, university, or admission probability. Treat personality as
one exploration signal, never a diagnosis or limitation. Treat the ICAR-16 cognitive score as
supporting evidence only: it is not a supervised clinical result and must never be used to limit a
student's options. Keep the language clear, encouraging, and concise."""


def build_context(profile, major_candidates, subject_strengths):
    """The only student data that leaves the server. Keep it free of identifiers."""
    return {
        'assessment_scores': latest_assessment_scores(profile),
        'academic_profile': {
            'grade': profile.grade,
            'gpa': profile.gpa,
            'sat_score': profile.sat_score,
            'ielts_score': profile.ielts_score,
        },
        'candidate_majors': major_candidates,
        'subject_strengths': subject_strengths,
    }


def _request_gateway(context):
    body = {
        'model': settings.EDUCATION_MATCH_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, default=str)},
        ],
        'response_format': {'type': 'json_object'},
        'temperature': 0,
        'stream': False,
        'max_completion_tokens': MAX_OUTPUT_TOKENS,
    }
    request = urllib.request.Request(
        settings.AI_GATEWAY_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.AI_GATEWAY_API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Vercel-AI-App-Name': 'Naseeb Edu',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=settings.AI_RECOMMENDATION_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    ai_usage.capture(payload, body)
    content = payload['choices'][0]['message']['content']
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(content).strip(), flags=re.IGNORECASE)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError('AI response must be a JSON object.')
    return result


def _cache_key(profile, context):
    # Everything the model sees (ranked majors, subjects, assessment versions and
    # scores, academic profile) plus the model and prompt, so any change misses.
    fingerprint = hashlib.sha256(json.dumps(
        [context, settings.EDUCATION_MATCH_MODEL, PROMPT_VERSION], sort_keys=True, default=str,
    ).encode('utf-8')).hexdigest()
    return f'education-guidance:{profile.pk}:{fingerprint}'


def generate_education_guidance(profile, major_candidates, subject_strengths):
    """Explain the student's ranked majors.

    Raises EducationAIUnavailable (AI off, no key, provider failure) or
    EducationAIBudgetExhausted. A repeat of the same input is served from cache
    without a provider call or a budget charge.
    """
    user = profile.user
    if not recommendation_ai_available():
        ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.LOCAL_FALLBACK)
        raise EducationAIUnavailable()
    context = build_context(profile, major_candidates, subject_strengths)
    cache_key = _cache_key(profile, context)
    cached = cache_get(cache_key)
    if cached:
        return cached
    if not ai_budget.consume(FEATURE, user):
        ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.BUDGET_REFUSED)
        raise EducationAIBudgetExhausted()
    ai_usage.begin()
    try:
        result = _validate_result(_request_gateway(context), major_candidates, subject_strengths)
        if not result['major_guidance']:
            raise ValueError('AI response did not contain an allowed major.')
    except (KeyError, IndexError, TypeError, ValueError, urllib.error.URLError, TimeoutError, OSError):
        logger.warning('education_ai_provider_failure student_id=%s', profile.pk)
        ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.FAILED)
        ai_budget.refund(FEATURE, user)
        raise EducationAIUnavailable()
    ai_usage.record(FEATURE, user, provider='gateway', status=ai_usage.OK)
    cache_set(cache_key, result, timeout=CACHE_TTL_SECONDS)
    return result
