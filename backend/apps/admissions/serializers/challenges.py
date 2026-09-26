"""Admissions API serializers — challenges."""
from rest_framework import serializers
from ..models import ChallengeAttempt


class ChallengeAttemptSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeAttempt
        fields = (
            'id', 'student', 'student_name', 'challenge', 'instrument_version',
            'answers', 'scores', 'completed_at', 'created_at',
        )
        # A student posts their own attempt; who it belongs to comes from the
        # request, never from the payload.
        read_only_fields = ('student', 'created_at')

    def get_student_name(self, obj) -> str:
        user = obj.student.user
        return user.get_full_name() or user.username

    def validate_challenge(self, value):
        if not value.strip():
            raise serializers.ValidationError('A challenge key is required.')
        return value.strip()

    def validate_answers(self, value):
        if not isinstance(value, dict) or not value:
            raise serializers.ValidationError('Answers must be a non-empty object.')
        for key, answer in value.items():
            if not isinstance(answer, int) or not 1 <= answer <= 5:
                raise serializers.ValidationError(f'Answer {key} must be a whole number from 1 to 5.')
        return value
