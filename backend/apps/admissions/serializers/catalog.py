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

    def get_programs(self, obj):
        programs = [
            program for program in obj.programs.all()
            if program.is_active and program.international_students_eligible
        ]
        return UniversityProgramSerializer(programs, many=True).data


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
