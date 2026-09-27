"""Admissions API views — research."""
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from apps.users.throttles import ScopedRateThrottle
from rest_framework.views import APIView
from apps.users.models import User
from ..models import University
from ..serializers import CollegeResearchProfileSerializer, EducationMatchAIRequestSerializer, UniversitySerializer
from ..education_ai import generate_education_guidance, recommendation_ai_available
from .common import COLLEGE_RESEARCH_LIMIT


COLLEGE_RESEARCH_QUESTIONS = {
    'gpa': {'label': 'Current GPA', 'type': 'number', 'placeholder': 'Example: 4.90', 'step': '0.01', 'min': 0, 'max': 100},
    'sat_score': {'label': 'SAT score', 'type': 'number', 'placeholder': 'Example: 1490', 'min': 400, 'max': 1600},
    'ielts_score': {'label': 'IELTS score', 'type': 'number', 'placeholder': 'Example: 7.0', 'step': '0.5', 'min': 0, 'max': 9},
    'target_major': {'label': 'Target major', 'type': 'text', 'placeholder': 'Example: Computer Science'},
    'target_countries': {'label': 'Target countries', 'type': 'text', 'placeholder': 'Example: USA, Canada, Singapore'},
    'budget_usd': {'label': 'Annual budget (USD)', 'type': 'number', 'placeholder': 'Example: 20000', 'min': 0, 'max': 500000},
}


def build_college_research(profile):
    required_fields = tuple(COLLEGE_RESEARCH_QUESTIONS)
    missing_fields = [field for field in required_fields if getattr(profile, field) in (None, '')]
    profile_counts = {
        'achievements': profile.achievements.count(),
        'honors': profile.honors.count(),
        'researches': profile.researches.count(),
        'projects': profile.projects.count(),
        'internships': profile.internships.count(),
        'activities': profile.activities.count(),
    }
    snapshot = {
        'gpa': profile.gpa,
        'gpa_scale': profile.effective_gpa_scale,
        'sat_score': profile.sat_score,
        'ielts_score': profile.ielts_score,
        'target_major': profile.target_major,
        'target_countries': profile.target_countries,
        'budget_usd': profile.budget_usd,
        'scholarship_needed': profile.scholarship_needed,
        'evidence': profile_counts,
    }
    if missing_fields:
        return {
            'ready': False,
            'missing_fields': missing_fields,
            'questions': [dict(field=field, **COLLEGE_RESEARCH_QUESTIONS[field]) for field in missing_fields],
            'profile_snapshot': snapshot,
            'recommendations': [],
        }

    sat = int(profile.sat_score)
    ielts = float(profile.ielts_score)
    gpa = float(profile.gpa)
    gpa_scale = int(profile.effective_gpa_scale)
    budget = int(profile.budget_usd)
    target_countries = [value.strip().lower() for value in profile.target_countries.split(',') if value.strip()]
    target_major = profile.target_major.strip().lower()
    evidence_total = sum(min(value, 2) for value in profile_counts.values())
    profile_strength_score = min(10, evidence_total * 2)
    recommendations = []

    for university in University.objects.filter(
        market__in=[
            University.Market.US,
            University.Market.CANADA,
            University.Market.CHINA,
            University.Market.HONG_KONG,
        ],
    ).prefetch_related('programs'):
        reasons = []
        gaps = []

        gpa_score = round(min(15, (gpa / gpa_scale) * 15))
        academic_score = gpa_score
        if university.sat_min:
            if sat >= (university.sat_max or university.sat_min):
                sat_score = 25
                reasons.append(f'SAT {sat} meets or exceeds the catalog range')
            elif sat >= university.sat_min:
                sat_score = 22
                reasons.append(f'SAT {sat} fits the {university.sat_min}–{university.sat_max or university.sat_min} catalog range')
            elif sat >= max(400, university.sat_min - 80):
                sat_score = 12
                gaps.append(f'SAT is {university.sat_min - sat} points below the catalog minimum')
            else:
                sat_score = 4
                gaps.append(f'Raise SAT toward at least {university.sat_min}')
        else:
            sat_score = 20
            reasons.append('No strict SAT minimum is listed in the catalog')
        academic_score += sat_score

        if ielts >= 7:
            academic_score += 8
            reasons.append(f'IELTS {ielts:g} is a strong language score')
        elif ielts >= 6.5:
            academic_score += 6
            reasons.append(f'IELTS {ielts:g} is suitable for many programs')
        else:
            academic_score += 3
            gaps.append('Verify the IELTS requirement on the official program page')

        preference_score = 0
        if university.country.lower() in target_countries:
            preference_score += 12
            reasons.append(f'{university.country} is one of your target countries')
        else:
            preference_score += 3
        active_programs = [
            program for program in university.programs.all()
            if program.is_active and program.international_students_eligible
        ]
        majors = [program.canonical_major.strip().lower() for program in active_programs]
        majors.extend(value.strip().lower() for value in university.popular_majors.split(',') if value.strip())
        if target_major and any(target_major in major or major in target_major for major in majors):
            preference_score += 10
            reasons.append(f'{profile.target_major} matches an available field of study')
        else:
            preference_score += 4
            gaps.append('Check the exact program requirements for your selected major')

        financial_score = 0
        if university.net_price_usd:
            if university.net_price_usd <= budget:
                financial_score += 12
                reasons.append('Estimated net price is within your budget')
            elif university.net_price_usd <= budget * 1.5:
                financial_score += 7
                gaps.append('Net price is above budget but may be covered with aid')
            else:
                financial_score += 2
                gaps.append('Estimated net price is significantly above your budget')
        else:
            financial_score += 5
            gaps.append('Net price is not available in the catalog')
        if profile.scholarship_needed:
            if university.offers_international_aid or university.offers_merit_aid or university.offers_need_based_aid:
                financial_score += 8
                reasons.append('A suitable type of financial aid is available')
            else:
                financial_score += 1
                gaps.append('International or merit aid is not listed in the catalog')
        else:
            financial_score += 8

        total_score = min(100, academic_score + preference_score + financial_score + profile_strength_score)
        acceptance_rate = float(university.acceptance_rate) if university.acceptance_rate is not None else None
        if (acceptance_rate is not None and acceptance_rate < 15) or (university.sat_min and sat < university.sat_min):
            admission_band = 'reach'
        elif acceptance_rate is not None and acceptance_rate >= 45 and (not university.sat_min or sat >= university.sat_min):
            admission_band = 'safety'
        else:
            admission_band = 'target'
        match_label = 'Strong match' if total_score >= 80 else 'Good match' if total_score >= 65 else 'Developing match'
        recommendations.append({
            'university': university,
            'match_score': total_score,
            'match_label': match_label,
            'admission_band': admission_band,
            'score_breakdown': {
                'academic': academic_score,
                'preferences': preference_score,
                'financial': financial_score,
                'profile_strength': profile_strength_score,
            },
            'reasons': reasons[:5],
            'gaps': gaps[:4],
        })

    recommendations.sort(key=lambda item: (-item['match_score'], item['university'].ranking or 999999))
    # Return (and serialize) only the best matches, not the whole catalog.
    recommendations = recommendations[:COLLEGE_RESEARCH_LIMIT]
    for item in recommendations:
        serialized_university = UniversitySerializer(item['university']).data
        matching_programs = [
            program for program in serialized_university['programs']
            if target_major and (
                target_major in program['canonical_major'].strip().lower()
                or program['canonical_major'].strip().lower() in target_major
            )
        ]
        item['university'] = serialized_university
        item['matched_programs'] = (matching_programs or serialized_university['programs'])[:5]
    return {
        'ready': True,
        'missing_fields': [],
        'questions': [],
        'profile_snapshot': snapshot,
        'recommendations': recommendations,
        'methodology': 'Academic fit, preferences, affordability, aid and verified profile evidence.',
        'generated_at': timezone.now(),
    }


class CollegeResearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_profile(self, request):
        if request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
            return None
        return request.user.student_profile

    def get(self, request):
        profile = self.get_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        return Response(build_college_research(profile))

    def post(self, request):
        profile = self.get_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        serializer = CollegeResearchProfileSerializer(data=request.data, context={'profile': profile})
        serializer.is_valid(raise_exception=True)
        serializer.update_profile(profile)
        return Response(build_college_research(profile))


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
