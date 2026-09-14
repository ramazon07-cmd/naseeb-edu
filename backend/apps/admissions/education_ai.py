"""De-identified AI explanations for assessment-ranked major matches."""

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger('naseeb.education_ai')
MAX_TEXT_LENGTH = 500
CURRENT_ASSESSMENTS = {'personality', 'interests', 'subjects', 'reasoning'}


def recommendation_ai_available():
    return bool(settings.GROQ_API_KEY)


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


def _fallback_guidance(major_candidates, subject_strengths):
    return {
        'mode': 'deterministic',
        'summary': 'These directions come from your completed assessments. Explore them with real courses and projects before deciding.',
        'major_guidance': [
            {
                'major': major,
                'why_fit': 'This major is among your highest-scoring assessment matches.',
                'subjects_to_focus': subject_strengths[:3],
                'explore_next': f'Try an introductory course or small project related to {major}.',
            }
            for major in major_candidates[:5]
        ],
        'questions_to_consider': [
            'Which recommended subject do you enjoy enough to study when it becomes difficult?',
            'Do you prefer creating, investigating, organizing, leading, or helping people?',
        ],
        'disclaimer': 'AI guidance is advisory and does not predict admission or define what you can study.',
    }


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
        'mode': 'groq',
        'summary': _safe_text(result.get('summary'), 'Your assessment-based education guidance is ready.'),
        'major_guidance': major_guidance,
        'questions_to_consider': questions,
        'disclaimer': 'AI guidance is advisory and does not predict admission or define what you can study.',
    }


def _request_groq(context):
    system_prompt = """You are an education exploration assistant for secondary-school students.
Return only a JSON object with: summary, major_guidance, questions_to_consider.
major_guidance items require major, why_fit, subjects_to_focus, explore_next.
Use only candidate majors and subjects supplied in the input. Never invent a program requirement,
ranking, cost, deadline, scholarship, university, or admission probability. Treat personality as
one exploration signal, never a diagnosis or limitation. Treat the ICAR-16 cognitive score as
supporting evidence only: it is not a supervised clinical result and must never be used to limit a
student's options. Keep the language clear, encouraging, and concise."""
    body = {
        'model': settings.GROQ_RECOMMENDATION_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, default=str)},
        ],
        'response_format': {'type': 'json_object'},
        'temperature': 0.2,
        'max_completion_tokens': 1200,
    }
    request = urllib.request.Request(
        settings.GROQ_API_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=settings.AI_RECOMMENDATION_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    content = payload['choices'][0]['message']['content']
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(content).strip(), flags=re.IGNORECASE)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError('AI response must be a JSON object.')
    return result


def generate_education_guidance(profile, major_candidates, subject_strengths):
    fallback = _fallback_guidance(major_candidates, subject_strengths)
    if not recommendation_ai_available():
        return fallback
    context = {
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
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode('utf-8')).hexdigest()
    cache_key = f'education-guidance:{profile.pk}:{fingerprint}'
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        result = _validate_result(_request_groq(context), major_candidates, subject_strengths)
        if not result['major_guidance']:
            raise ValueError('AI response did not contain an allowed major.')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        logger.warning('education_ai_provider_failure student_id=%s', profile.pk)
        return fallback
    cache.set(cache_key, result, timeout=24 * 60 * 60)
    return result
