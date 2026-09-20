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
DEFAULT_MINOR_CANDIDATES = [
    'Psychology', 'Design', 'Entrepreneurship', 'Data Science', 'Philosophy',
    'Communication', 'Public Policy', 'Sustainability', 'Economics',
    'Linguistics', 'Statistics', 'Anthropology',
]


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


def _fallback_minors(primary_major, minor_candidates):
    name = primary_major.casefold()
    if any(word in name for word in ('computer', 'data', 'engineering', 'mathematics')):
        preferred = ['Psychology', 'Design', 'Entrepreneurship']
    elif any(word in name for word in ('business', 'economics', 'finance', 'management')):
        preferred = ['Data Science', 'Psychology', 'Sustainability']
    elif any(word in name for word in ('biology', 'chemistry', 'medicine', 'health', 'agronomy')):
        preferred = ['Data Science', 'Communication', 'Public Policy']
    elif any(word in name for word in ('art', 'design', 'music', 'media', 'literature')):
        preferred = ['Psychology', 'Entrepreneurship', 'Data Science']
    else:
        preferred = ['Psychology', 'Design', 'Entrepreneurship']
    ordered = preferred + [minor for minor in minor_candidates if minor not in preferred]
    return [minor for minor in ordered if minor in minor_candidates][:3]


def _fallback_guidance(major_candidates, subject_strengths, minor_candidates):
    primary_major = major_candidates[0]
    minors = _fallback_minors(primary_major, minor_candidates)
    return {
        'mode': 'deterministic',
        'summary': 'One strong foundation, with three distinctive ways to make it yours.',
        'strongest_major': {
            'major': primary_major,
            'why_fit': 'This is your highest-scoring match across the completed assessments.',
            'evidence': subject_strengths[:3],
            'explore_next': f'Try an introductory course or small project related to {primary_major}.',
        },
        'minor_guidance': [
            {
                'minor': minor,
                'why_fit': f'{minor} adds a different perspective to your strongest major.',
                'combination_idea': f'Explore a small project that combines {primary_major} with {minor}.',
            }
            for minor in minors
        ],
        'questions_to_consider': [
            'Would you still enjoy this major when the work becomes difficult?',
            'Which minor would make your future work feel more personal to you?',
        ],
        'disclaimer': 'This guidance supports exploration. Minor names and availability vary by university.',
    }


def _validate_result(result, major_candidates, subject_strengths, minor_candidates):
    allowed_majors = {major.casefold(): major for major in major_candidates}
    allowed_subjects = {subject.casefold(): subject for subject in subject_strengths}
    allowed_minors = {minor.casefold(): minor for minor in minor_candidates}
    item = result.get('strongest_major', {})
    major = allowed_majors.get(str(item.get('major', '')).casefold()) if isinstance(item, dict) else None
    evidence = []
    if major:
        for subject in item.get('evidence', []):
            matched = allowed_subjects.get(str(subject).casefold())
            if matched and matched not in evidence:
                evidence.append(matched)
    strongest_major = {
        'major': major,
        'why_fit': _safe_text(item.get('why_fit'), 'This major aligns with your assessment profile.'),
        'evidence': evidence[:4],
        'explore_next': _safe_text(item.get('explore_next'), f'Explore an introductory {major} project.'),
    } if major else None
    minor_guidance = []
    for minor_item in result.get('minor_guidance', []):
        if not isinstance(minor_item, dict):
            continue
        minor = allowed_minors.get(str(minor_item.get('minor', '')).casefold())
        if not minor or any(row['minor'] == minor for row in minor_guidance):
            continue
        minor_guidance.append({
            'minor': minor,
            'why_fit': _safe_text(minor_item.get('why_fit'), f'{minor} adds a complementary perspective.'),
            'combination_idea': _safe_text(minor_item.get('combination_idea'), f'Explore how {minor} connects with {major}.'),
        })
    questions = [_safe_text(question) for question in result.get('questions_to_consider', []) if _safe_text(question)][:4]
    return {
        'mode': 'groq',
        'summary': _safe_text(result.get('summary'), 'Your assessment-based education guidance is ready.'),
        'strongest_major': strongest_major,
        'minor_guidance': minor_guidance[:3],
        'questions_to_consider': questions,
        'disclaimer': 'This guidance supports exploration. Minor names and availability vary by university.',
    }


def _request_groq(context):
    system_prompt = """You are an education exploration assistant for secondary-school students.
Return only a JSON object with: summary, strongest_major, minor_guidance, questions_to_consider.
strongest_major requires major, why_fit, evidence, explore_next. Choose exactly one major: the
strongest evidence-based fit from candidate_majors. minor_guidance must contain exactly three
distinct items with minor, why_fit, combination_idea. Choose only from candidate_minors. Prefer
complementary and somewhat unexpected combinations over three obvious specializations of the major.
Use only candidate majors, minors, and subjects supplied in the input. Never invent a program requirement,
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


def generate_education_guidance(profile, major_candidates, subject_strengths, minor_candidates=None):
    minor_candidates = minor_candidates or DEFAULT_MINOR_CANDIDATES
    fallback = _fallback_guidance(major_candidates, subject_strengths, minor_candidates)
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
        'candidate_minors': minor_candidates,
        'subject_strengths': subject_strengths,
    }
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode('utf-8')).hexdigest()
    cache_key = f'education-guidance:{profile.pk}:{fingerprint}'
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        result = _validate_result(_request_groq(context), major_candidates, subject_strengths, minor_candidates)
        if not result['strongest_major'] or len(result['minor_guidance']) != 3:
            raise ValueError('AI response did not contain one allowed major and three allowed minors.')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        logger.warning('education_ai_provider_failure student_id=%s', profile.pk)
        return fallback
    cache.set(cache_key, result, timeout=24 * 60 * 60)
    return result
