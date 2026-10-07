"""Admissions API views — research."""
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from apps.users.throttles import ScopedRateThrottle
from rest_framework.views import APIView
from apps.users.models import User
from ..college_search import CollegeSearchParams, college_search, evidence_counts, missing_fields
from ..serializers import CollegeResearchProfileSerializer, EducationMatchAIRequestSerializer
from ..education_ai import generate_education_guidance, recommendation_ai_available


COLLEGE_RESEARCH_QUESTIONS = {
    'gpa': {'label': 'Current GPA', 'type': 'number', 'placeholder': 'Example: 4.90', 'step': '0.01', 'min': 0, 'max': 100},
    'sat_score': {'label': 'SAT score', 'type': 'number', 'placeholder': 'Example: 1490', 'min': 400, 'max': 1600},
    'ielts_score': {'label': 'IELTS score', 'type': 'number', 'placeholder': 'Example: 7.0', 'step': '0.5', 'min': 0, 'max': 9},
    'target_major': {'label': 'Target major', 'type': 'text', 'placeholder': 'Example: Computer Science'},
    'target_countries': {'label': 'Target countries', 'type': 'text', 'placeholder': 'Example: USA, Canada, Singapore'},
    'budget_usd': {'label': 'Annual budget (USD)', 'type': 'number', 'placeholder': 'Example: 20000', 'min': 0, 'max': 500000},
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
            'budget_usd': profile.budget_usd,
            'scholarship_needed': profile.scholarship_needed,
            'evidence': evidence,
        },
        'methodology': 'Academic fit, preferences, affordability, aid and verified profile evidence.',
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
