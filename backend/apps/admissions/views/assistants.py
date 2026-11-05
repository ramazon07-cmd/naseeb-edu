"""Admissions API views — counselor assistants: invitations, students, accepting."""
from django.db.models import Count, Q
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User
from apps.users.throttles import (
    InviteAcceptIPThrottle, InviteAttemptIPThrottle, InviteTokenThrottle, ScopedRateThrottle,
)

from ..assistants import (
    MAX_ASSISTANT_STUDENTS,
    AssistantInviteCreateSerializer,
    accept_assistant_invite,
    accept_path,
    assistant_invite_public_info,
    assistants_of,
    can_manage_assistants,
    create_assistant_invite,
    deactivate_assistant,
    find_assistant_invite,
    revoke_assistant_invite,
    send_assistant_invite_email,
    set_assistant_students,
)
from ..invites import InviteUnavailable
from ..models import AssistantInvite

class CounselorManagesAssistants(permissions.BasePermission):
    message = 'Only a counselor can manage assistants.'

    def has_permission(self, request, view):
        return can_manage_assistants(request.user)


class AssistantInviteSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = AssistantInvite
        fields = ('id', 'status', 'email', 'first_name', 'last_name', 'created_at', 'expires_at', 'accepted_at', 'revoked_at')
        read_only_fields = fields


class AssistantSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    students_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'is_active', 'last_login', 'date_joined', 'students_count')
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class AssistantStudentsSerializer(serializers.Serializer):
    students = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True, max_length=MAX_ASSISTANT_STUDENTS,
    )


class AssistantInviteViewSet(viewsets.GenericViewSet):
    """A counselor's assistant invitations: create (emailed), list, revoke."""

    serializer_class = AssistantInviteSerializer
    permission_classes = [permissions.IsAuthenticated, CounselorManagesAssistants]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == 'create':
            self.throttle_scope = 'credential_issue'
            throttles.append(ScopedRateThrottle())
        return throttles

    def get_queryset(self):
        return AssistantInvite.objects.filter(counselor=self.request.user, school_id=self.request.user.school_id)

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def create(self, request):
        serializer = AssistantInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite, raw = create_assistant_invite(counselor=request.user, data=serializer.validated_data)
        emailed = send_assistant_invite_email(invite, raw, request)
        return Response({
            **AssistantInviteSerializer(invite).data,
            # Shown once: only the token's hash is stored.
            'path': accept_path(raw),
            'emailed': emailed,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        return Response(AssistantInviteSerializer(revoke_assistant_invite(self.get_object(), request.user)).data)


class AssistantViewSet(viewsets.GenericViewSet):
    """A counselor's assistants: list them, give them students, deactivate them."""

    serializer_class = AssistantSerializer
    permission_classes = [permissions.IsAuthenticated, CounselorManagesAssistants]

    def get_queryset(self):
        counselor = self.request.user
        # Counted the way the assistant sees them: still this counselor's, active students.
        return assistants_of(counselor).annotate(students_count=Count('assisted_students', filter=Q(
            assisted_students__assigned_counselor=counselor, assisted_students__user__is_active=True,
            assisted_students__deactivated_at__isnull=True,
        ))).order_by('-is_active', 'first_name', 'last_name', 'id')

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=['put'])
    def students(self, request, pk=None):
        """Replace the assistant's students with ``students`` (ids of the counselor's own students)."""
        assistant = self.get_object()
        if not assistant.is_active:
            return Response({'detail': 'This assistant is deactivated.'}, status=400)
        serializer = AssistantStudentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = set_assistant_students(counselor=request.user, assistant=assistant, student_ids=serializer.validated_data['students'])
        return Response({'id': assistant.pk, 'students': ids})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        assistant = deactivate_assistant(counselor=request.user, assistant=self.get_object())
        return Response({'id': assistant.pk, 'is_active': assistant.is_active})


class PublicAssistantInviteView(APIView):
    """GET: what the invitation page shows. Same 404 for every unusable token."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'invite_public'

    def get(self, request, token):
        invite = find_assistant_invite(token)
        if invite is None:
            raise InviteUnavailable(request)
        response = Response(assistant_invite_public_info(invite))
        response['Cache-Control'] = 'private, no-store'
        return response


class PublicAssistantInviteAcceptView(APIView):
    """POST: the assistant sets their username and password; the account is ready to sign in."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InviteAttemptIPThrottle, InviteTokenThrottle]

    def post(self, request, token):
        created = InviteAcceptIPThrottle()
        if not created.allow_request(request, self):
            self.throttled(request, created.wait())
        try:
            user, invite = accept_assistant_invite(token, request.data, request)
        except Exception:
            created.refund()
            raise
        return Response({
            'status': 'ready',
            'username': user.username,
            'school_name': invite.school.name,
            'counselor_name': invite.counselor.get_full_name() or invite.counselor.username,
        }, status=status.HTTP_201_CREATED)
