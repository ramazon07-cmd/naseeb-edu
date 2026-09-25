"""Admissions API serializers — essays."""
from rest_framework import serializers
from ..models import Essay, EssayRevision
from .common import GoogleDocsModelSerializer, StudentRecordSerializerMixin, google_docs_preview_url


class EssayRevisionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = EssayRevision
        # The revision history lists versions only. Copying each revision's text
        # into every list response doubled its size (it is never displayed).
        fields = ('id', 'essay', 'version', 'status', 'created_by', 'created_by_name', 'created_at')


class EssaySerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()
    university_name = serializers.SerializerMethodField()
    revisions = EssayRevisionSerializer(many=True, read_only=True)

    class Meta:
        model = Essay
        # Explicit legacy shape. The Essay Lab fields (doc, save_seq, folder, word_count, ...)
        # are neither returned nor writable here; students edit them through /api/essay-lab/.
        fields = (
            'id', 'student', 'application', 'title', 'prompt', 'content', 'version', 'status',
            'counselor_comment', 'google_docs_url', 'created_at', 'updated_at',
            'student_name', 'university_name', 'revisions', 'google_docs_preview_url',
            'shared_with_counselor', 'shared_at',
        )
        # Only the student shares or unshares, through the Essay Lab.
        read_only_fields = ('version', 'shared_with_counselor', 'shared_at')

    def _is_counselor(self):
        request = self.context.get('request')
        return bool(request and request.user.is_counselor_like)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        if not self._is_counselor():
            # Counselor feedback is read-only for everyone else.
            values.pop('counselor_comment', None)
        return values

    def validate_status(self, value):
        current = getattr(self.instance, 'status', None)
        if not self._is_counselor() and value == Essay.Status.APPROVED and current != Essay.Status.APPROVED:
            raise serializers.ValidationError('Only a counselor can approve essays.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # An essay can only point at an application of the same student.
        student = attrs.get('student') or getattr(self.instance, 'student', None)
        application = attrs['application'] if 'application' in attrs else getattr(self.instance, 'application', None)
        if application is not None and student is not None and application.student_id != student.pk:
            raise serializers.ValidationError({'application': 'This application belongs to a different student.'})
        return attrs

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_university_name(self, obj) -> str | None:
        return obj.application.university.name if obj.application else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in (
                'prompt', 'content', 'counselor_comment', 'google_docs_url', 'google_docs_preview_url', 'revisions',
                'doc', 'preview', 'folder',
            ):
                data.pop(field, None)
        return data


