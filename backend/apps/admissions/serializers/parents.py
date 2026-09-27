"""Admissions API serializers — parents."""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from apps.users.models import User
from ..models import ParentStudentLink, StudentProfile


class ParentStudentLinkSerializer(serializers.ModelSerializer):
    parent_name = serializers.SerializerMethodField()
    parent_email = serializers.EmailField(source='parent.email', read_only=True)
    student_name = serializers.SerializerMethodField()
    relationship_display = serializers.CharField(source='get_relationship_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ParentStudentLink
        fields = (
            'id', 'parent', 'parent_name', 'parent_email', 'student', 'student_name',
            'relationship', 'relationship_display', 'status', 'status_display',
            'can_view_applications', 'can_view_documents', 'can_view_meetings',
            'invited_by', 'invited_at', 'consented_at', 'revoked_at', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_parent_name(self, obj):
        return obj.parent.get_full_name() or obj.parent.username

    def get_student_name(self, obj):
        return obj.student.user.get_full_name() or obj.student.user.username


class ParentInviteSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.select_related('user', 'school'),
        error_messages={
            'does_not_exist': 'Select one of your assigned students.',
            'incorrect_type': 'Select one of your assigned students.',
        },
    )
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    # Always required, so the response cannot reveal whether the address
    # already has an account.
    password = serializers.CharField(write_only=True, allow_blank=False, validators=[validate_password])
    relationship = serializers.ChoiceField(choices=ParentStudentLink.Relationship.choices)
    can_view_applications = serializers.BooleanField(default=True)
    can_view_documents = serializers.BooleanField(default=True)
    can_view_meetings = serializers.BooleanField(default=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the lookup itself, so a missing id and another counselor's
        # student produce the same error (no student-id enumeration).
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and not user.is_product_admin:
            field = self.fields['student']
            if user.role == User.Role.COUNSELOR and user.school_id:
                field.queryset = field.queryset.filter(assigned_counselor=user, school_id=user.school_id)
            else:
                field.queryset = field.queryset.none()
