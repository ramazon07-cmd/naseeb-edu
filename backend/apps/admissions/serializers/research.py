"""Admissions API serializers — research."""
from rest_framework import serializers
from ..models import StudentProfile
from .common import validate_gpa_on_scale


class CollegeResearchProfileSerializer(serializers.Serializer):
    gpa = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    gpa_scale = serializers.ChoiceField(choices=StudentProfile.GpaScale.choices, required=False)
    ielts_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=9, required=False)
    sat_score = serializers.IntegerField(min_value=400, max_value=1600, required=False)
    target_major = serializers.CharField(max_length=160, required=False, allow_blank=False)
    target_countries = serializers.CharField(max_length=255, required=False, allow_blank=False)
    budget_usd = serializers.IntegerField(min_value=0, max_value=500000, required=False)
    scholarship_needed = serializers.BooleanField(required=False)

    def validate(self, attrs):
        profile = self.context.get('profile')
        gpa = attrs.get('gpa', getattr(profile, 'gpa', None))
        scale = attrs.get('gpa_scale') or (
            getattr(profile, 'gpa_scale', None) if 'gpa' not in attrs else None
        ) or StudentProfile.infer_gpa_scale(gpa)
        validate_gpa_on_scale(gpa, scale)
        if 'gpa' in attrs and 'gpa_scale' not in attrs:
            attrs['gpa_scale'] = scale
        return attrs

    def update_profile(self, profile):
        for field, value in self.validated_data.items():
            setattr(profile, field, value)
        if self.validated_data:
            profile.save(update_fields=[*self.validated_data.keys(), 'updated_at'])
        return profile


class EducationMatchAIRequestSerializer(serializers.Serializer):
    major_candidates = serializers.ListField(
        child=serializers.CharField(max_length=160),
        min_length=1,
        max_length=8,
    )
    subject_strengths = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        max_length=12,
    )

    def validate(self, attrs):
        for field in ('major_candidates', 'subject_strengths'):
            values = attrs.get(field, [])
            attrs[field] = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not attrs['major_candidates']:
            raise serializers.ValidationError({'major_candidates': 'Provide at least one major candidate.'})
        return attrs
