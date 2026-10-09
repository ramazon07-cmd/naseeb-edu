"""Admissions API serializers — catalog."""
from rest_framework import serializers

from ..pricing import cost_fields, forget_cost
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
        exclude = ('search_text',)
        read_only_fields = ('qs_data',)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        forget_cost(instance)
        return instance

    def to_representation(self, instance):
        return {**super().to_representation(instance), **cost_fields(instance)}

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
            'id', 'name', 'city', 'country', 'market', 'institution_type', 'ranking', 'ranking_label', 'qs_data',
            'acceptance_rate', 'sat_min', 'sat_max', 'test_optional', 'net_price_usd', 'intl_cost_usd', 'offers_international_aid',
            'application_deadline', 'scholarship_deadline',
        )

    def to_representation(self, instance):
        return {**super().to_representation(instance), **cost_fields(instance)}

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


# Plausible bounds for the numbers the admin catalogue edits. DRF's own
# min/max messages are already translated (apps/users/api_messages.py).
SAT = {'min_value': 400, 'max_value': 1600}
ACT = {'min_value': 1, 'max_value': 36}
IELTS = {'min_value': 0, 'max_value': 9}
PERCENT = {'min_value': 0, 'max_value': 100}
NOT_NEGATIVE = {'min_value': 0}


def check_min_max(serializer, attrs, pairs):
    """No (low, high) pair may end up reversed, counting the values this edit leaves alone."""
    def value(name):
        return attrs.get(name, getattr(serializer.instance, name, None))

    errors = {
        high: ['The maximum must not be below the minimum.']
        for low, high in pairs
        if value(low) is not None and value(high) is not None and value(low) > value(high)
    }
    if errors:
        raise serializers.ValidationError(errors)


class CatalogUniversitySerializer(serializers.ModelSerializer):
    """A university as the admin catalogue edits it; its programs are edited on their own."""

    programs_count = serializers.IntegerField(read_only=True)
    applications_count = serializers.IntegerField(read_only=True)
    scholarships_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = University
        # QS scores are imported (load_qs_rankings), never typed in.
        exclude = ('qs_data',)
        read_only_fields = ('market',)
        extra_kwargs = {
            'sat_min': SAT, 'sat_max': SAT, 'act_min': ACT, 'act_max': ACT,
            'acceptance_rate': PERCENT, 'students_receiving_aid_percent': PERCENT,
        }

    def validate(self, attrs):
        check_min_max(self, attrs, (('sat_min', 'sat_max'), ('act_min', 'act_max')))
        if 'country' in attrs:
            # Model.save only sets recognized markets; an edit must also clear
            # an old market when moving a university outside those markets.
            attrs['market'] = University.market_for_country(attrs['country'])
        return attrs


class CatalogProgramSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = UniversityProgram
        fields = '__all__'
        extra_kwargs = {
            'sat_min': SAT, 'ielts_min': IELTS, 'toefl_min': {'min_value': 0, 'max_value': 120},
            'min_gpa': NOT_NEGATIVE, 'duration_years': NOT_NEGATIVE,
        }


class CatalogScholarshipSerializer(ScholarshipSerializer):
    class Meta(ScholarshipSerializer.Meta):
        extra_kwargs = {'min_sat': SAT, 'min_ielts': IELTS, 'min_gpa': NOT_NEGATIVE}


class CatalogOpportunityProgramSerializer(OpportunityProgramSerializer):
    class Meta(OpportunityProgramSerializer.Meta):
        # The catalogue importer owns these.
        read_only_fields = ('source_key', 'source_metadata')

    def validate(self, attrs):
        check_min_max(self, attrs, (('start_date', 'end_date'),))
        return attrs


class StoreItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreItem
        fields = '__all__'
