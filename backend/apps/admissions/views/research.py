"""Admissions API views — research."""
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from apps.users.throttles import ScopedRateThrottle
from rest_framework.views import APIView
from apps.users.models import User
from .. import match_reasons
from ..college_match import college_match, match_with_context
from ..college_search import (
    CollegeSearchParams, college_search, evidence_counts, fit_key, missing_fields,
)
from ..serializers import CollegeResearchProfileSerializer, EducationMatchAIRequestSerializer
from ..education_ai import generate_education_guidance, recommendation_ai_available


COLLEGE_RESEARCH_QUESTIONS = {
    'gpa': {'label': 'Current GPA', 'type': 'number', 'placeholder': 'Example: 4.90', 'step': '0.01', 'min': 0, 'max': 100},
    'sat_score': {'label': 'SAT score', 'type': 'number', 'placeholder': 'Example: 1490', 'min': 400, 'max': 1600},
    'ielts_score': {'label': 'IELTS score', 'type': 'number', 'placeholder': 'Example: 7.0', 'step': '0.5', 'min': 0, 'max': 9},
    'target_major': {'label': 'Target major', 'type': 'text', 'placeholder': 'Example: Computer Science'},
    'target_countries': {'label': 'Target countries', 'type': 'text', 'placeholder': 'Example: USA, Canada, Singapore'},
}


def build_college_research(profile):
    """The student's research profile: what is still missing and the answers College Search ranks by.

    Each university's fit travels with its row in College Search (``college_search``), so
    opening the page no longer scores the whole catalogue.
    """
    evidence = evidence_counts(profile)
    missing = missing_fields(profile)
    return {
        'ready': not missing,
        'missing_fields': missing,
        'questions': [dict(field=field, **COLLEGE_RESEARCH_QUESTIONS[field]) for field in missing],
        'profile_snapshot': {
            'gpa': profile.gpa,
            'gpa_scale': profile.effective_gpa_scale,
            'sat_score': profile.sat_score,
            'ielts_score': profile.ielts_score,
            'target_major': profile.target_major,
            'target_countries': profile.target_countries,
            'scholarship_needed': profile.scholarship_needed,
            'evidence': evidence,
        },
        'methodology': 'Academic fit, preferences, aid and verified profile evidence.',
        'generated_at': timezone.now(),
    }


def student_profile(request):
    if request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
        return None
    return request.user.student_profile


class CollegeResearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = student_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        return Response(build_college_research(profile))

    def post(self, request):
        profile = student_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        serializer = CollegeResearchProfileSerializer(data=request.data, context={'profile': profile})
        serializer.is_valid(raise_exception=True)
        serializer.update_profile(profile)
        return Response(build_college_research(profile))


class CollegeSearchView(APIView):
    """One page of College Search (``GET /api/college-search/``), ranked for the student."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = student_profile(request)
        if not profile:
            return Response({'detail': 'College Search is available to student accounts only.'}, status=403)
        params = CollegeSearchParams(data=request.query_params)
        params.is_valid(raise_exception=True)
        return Response(college_search(profile, params.validated_data))


class EducationMatchAIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'assistant'

    def post(self, request):
        if request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
            return Response({'detail': 'Education match guidance is available to student accounts only.'}, status=403)
        serializer = EducationMatchAIRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = request.user.student_profile
        result = generate_education_guidance(
            profile=profile,
            major_candidates=serializer.validated_data['major_candidates'],
            subject_strengths=serializer.validated_data.get('subject_strengths', []),
        )
        result['provider_available'] = recommendation_ai_available()
        return Response(result)


class CollegeMatchView(APIView):
    """The college match (``POST /api/college-match/``): ten universities for the student's major.

    Chosen with fixed rules (college_match.py), never by AI: this call makes no AI request.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile = student_profile(request)
        if not profile:
            return Response({'detail': 'The college match is available to student accounts only.'}, status=403)
        missing = missing_fields(profile)
        if missing:
            return Response({'detail': 'Complete your research profile first.', 'missing_fields': missing}, status=400)
        data = college_match(profile)
        data['generated_at'] = timezone.now()
        return Response(data)


class CollegeMatchReasonsView(APIView):
    """The optional "Why these fit you" lines (``POST /api/college-match/reasons/``).

    One AI call writes one line for each card of the match; it counts as one unit of the daily limit,
    is cached for the same list and profile, and answers 503 (unit given back) when it fails.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'assistant'

    def post(self, request):
        profile = student_profile(request)
        if not profile:
            return Response({'detail': 'The college match is available to student accounts only.'}, status=403)
        missing = missing_fields(profile)
        if missing:
            return Response({'detail': 'Complete your research profile first.', 'missing_fields': missing}, status=400)
        data, ctx = match_with_context(profile)
        language = str(request.data.get('language') or 'en')[:5]
        try:
            lines, cached = match_reasons.generate(
                profile, request.user, data, fit_key(profile, ctx), ctx['rubric'], language)
        except match_reasons.ReasonsUnavailable as unavailable:
            detail = ('Naseeb AI is resting for today. Please try again tomorrow.' if unavailable.code == 'coach_resting'
                      else 'Naseeb AI is unavailable right now. Please try again soon.')
            return Response({'detail': detail, 'code': unavailable.code}, status=unavailable.status)
        return Response({'reasons': lines, 'cached': cached})
