"""Admissions API serializers — challenges."""
from rest_framework import serializers
from ..models import ChallengeAttempt

# Every challenge is answered on a 1-5 scale except the ICAR-16 reasoning test,
# whose answer is the option picked: up to eight (the 3D rotation items, A-H).
ANSWER_MAX = {'reasoning': 8}
SCALE_MAX = 5


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
        return value

    def validate(self, attrs):
        top = ANSWER_MAX.get(attrs['challenge'], SCALE_MAX)
        for key, answer in attrs.get('answers', {}).items():
            # bool is an int in Python; true/false is not an answer.
            if isinstance(answer, bool) or not isinstance(answer, int) or not 1 <= answer <= top:
                raise serializers.ValidationError({'answers': [f'Answer {key} must be a whole number from 1 to {top}.']})
        return attrs
