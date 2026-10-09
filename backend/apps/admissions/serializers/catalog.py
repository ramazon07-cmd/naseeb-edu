"""Admissions API serializers — catalog."""
from rest_framework import serializers
from ..models import (
    OpportunityProgram,
    Scholarship,
    StoreItem,
    University,
    UniversityProgram,
)


class UniversityProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = UniversityProgram
        fields = '__all__'


class UniversitySerializer(serializers.ModelSerializer):
    programs = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = '__all__'
        read_only_fields = ('qs_data',)

    def get_programs(self, obj):
        programs = [
            program for program in obj.programs.all()
            if program.is_active and program.international_students_eligible
        ]
        return UniversityProgramSerializer(programs, many=True).data


# The QS values the College Search table shows and filters by; the detail view has them all.
QS_LIST_KEYS = ('region', 'size', 'focus', 'research', 'status', 'overall_score')
QS_LIST_INDICATORS = ('AR', 'ER', 'CPF', 'ISR', 'SUS')


class UniversityRowSerializer(serializers.ModelSerializer):
    """A university as one row of a list: what College Search and the pickers show.

    The full record (programs, aid details, notes, URLs, timestamps) is served
    by the detail endpoint, so a page of rows stays small on a slow connection.
    College Search adds the program names it needs (``college_search.serialize_rows``).
    """

    qs_data = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = (
            'id', 'name', 'city', 'country', 'institution_type', 'ranking', 'ranking_label', 'qs_data',
            'acceptance_rate', 'sat_min', 'sat_max', 'test_optional', 'net_price_usd', 'intl_cost_usd',
            'application_deadline', 'scholarship_deadline',
        )

    def get_qs_data(self, obj):
        data = obj.qs_data or {}
        if not data:
            return {}
        indicators = data.get('indicators') or {}
        return {
            **{key: data[key] for key in QS_LIST_KEYS if key in data},
            'indicators': {code: {'score': indicators[code].get('score')} for code in QS_LIST_INDICATORS if code in indicators},
        }


class ScholarshipSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = Scholarship
        fields = '__all__'


class OpportunityProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityProgram
        fields = '__all__'


class StoreItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreItem
        fields = '__all__'
