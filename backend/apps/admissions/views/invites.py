"""Admissions API views — student invites, magic links and the pending-student queue."""
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import entitlements
from apps.users.localization import localized_message
from apps.users.throttles import (
    InviteAcceptIPThrottle, InviteAttemptIPThrottle, InviteTokenThrottle, ScopedRateThrottle,
)
from core.exceptions import CodedError

from ..invites import (
    confirmed_in_scope,
    InviteCreateSerializer,
    InviteSerializer,
    InviteUnavailable,
    PendingStudentSerializer,
    accept_invite,
    can_create_invites,
    confirm_student,
    create_invite,
    find_invite,
    invite_public_info,
    invite_scope,
    join_path,
    pending_scope,
    reject_student,
    revoke_invite,
    school_counselors,
    self_join_enabled,
    usable_invites,
)

LIST_LIMIT = 100
PENDING_LIMIT = 200
SELF_JOIN_DISABLED_MESSAGE = 'Students get their login from their counselor. Create the student account instead.'


class StudentInviteViewSet(viewsets.GenericViewSet):
    """Counselors' invites: create (personal or magic link), list, revoke."""

    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return invite_scope(self.request.user)

    def list(self, request):
        queryset = self.get_queryset()
        if request.query_params.get('status') == 'active':
            queryset = queryset.filter(pk__in=usable_invites().values('pk'))
        kind = request.query_params.get('kind')
        if kind in {'personal', 'link'}:
            queryset = queryset.filter(kind=kind)
        return Response(InviteSerializer(queryset[:LIST_LIMIT], many=True).data)

    def create(self, request):
        if not can_create_invites(request.user):
            return Response({'detail': 'Only counselors can invite students.'}, status=403)
        if not self_join_enabled():
            return Response({'detail': SELF_JOIN_DISABLED_MESSAGE, 'code': 'self_join_disabled'}, status=403)
        serializer = InviteCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        invite, raw = create_invite(actor=request.user, data=serializer.validated_data)
        return Response({
            **InviteSerializer(invite).data,
            # Shown once: only the token's hash is stored.
            'token': raw,
            'path': join_path(raw),
            # No outgoing mail is configured; the counselor copies the link.
            'emailed': False,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def counselors(self, request):
        """Who students can be invited for: an organization's counselors, or the counselor themselves."""
        return Response([
            {'id': counselor.pk, 'name': counselor.get_full_name() or counselor.username}
            for counselor in school_counselors(request.user)[:LIST_LIMIT]
        ])

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        invite = self.get_object()
        return Response(InviteSerializer(revoke_invite(invite, request.user)).data)


class PendingStudentViewSet(viewsets.GenericViewSet):
    """Students who joined by invite and wait for their counselor: list, confirm, reject."""

    serializer_class = PendingStudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return pending_scope(self.request.user).select_related(
            'user', 'assigned_counselor', 'joined_invite',
        ).order_by('-created_at', '-id')

    def list(self, request):
        return Response(PendingStudentSerializer(self.get_queryset()[:PENDING_LIMIT], many=True).data)

    def _already_confirmed(self, request, pk):
        # Confirmed by someone else first: no longer pending, so get_object would 404.
        return Response({
            'id': int(pk), 'status': 'confirmed', 'code': 'already_confirmed',
            'detail': localized_message('already_confirmed', request),
        }, status=status.HTTP_409_CONFLICT)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        if str(pk).isdigit() and confirmed_in_scope(request.user, int(pk)):
            return Response({'id': int(pk), 'status': 'confirmed'})
        try:
            profile = confirm_student(self.get_object(), request.user)
        except entitlements.EntitlementError as exc:
            raise _entitlement_error(exc, request) from exc
        return Response({'id': profile.pk, 'status': 'confirmed'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if str(pk).isdigit() and confirmed_in_scope(request.user, int(pk)):
            return self._already_confirmed(request, pk)
        outcome = reject_student(self.get_object(), request.user)
        if outcome == 'confirmed':
            # Confirmed by someone else meanwhile: nothing was removed.
            return self._already_confirmed(request, pk)
        # outcome: 'deleted' (the account is gone) or 'deactivated' (kept, cannot sign in).
        return Response({'id': int(pk), 'status': 'rejected', 'outcome': outcome})


def _entitlement_error(exc, request):
    code = 'school_full' if exc.code == 'seat_limit_reached' else exc.code
    return CodedError(localized_message(code, request), code)


class PublicInviteView(APIView):
    """GET: what the join page shows for a token. Same 404 for every unusable token."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'invite_public'

    def get(self, request, token):
        invite = find_invite(token) if self_join_enabled() else None
        if invite is None:
            raise InviteUnavailable(request)
        response = Response(invite_public_info(invite))
        response['Cache-Control'] = 'private, no-store'
        return response


class PublicInviteAcceptView(APIView):
    """POST: create the student's account from the invite; it waits for confirmation.

    Every attempt counts per IP and per token; only successful sign-ups count
    against the per-IP account-creation rate.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InviteAttemptIPThrottle, InviteTokenThrottle]

    def post(self, request, token):
        if not self_join_enabled():
            # Old links answer like any unusable token.
            raise InviteUnavailable(request)
        created = InviteAcceptIPThrottle()
        if not created.allow_request(request, self):
            self.throttled(request, created.wait())
        try:
            profile, invite = accept_invite(token, request.data, request)
        except entitlements.EntitlementError as exc:
            created.refund()
            raise _entitlement_error(exc, request) from exc
        except Exception:
            created.refund()
            raise
        return Response({
            'status': 'pending',
            'username': profile.user.username,
            'school_name': invite.school.name,
            'counselor_name': invite.counselor.get_full_name() or invite.counselor.username,
        }, status=status.HTTP_201_CREATED)
