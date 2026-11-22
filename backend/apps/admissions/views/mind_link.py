"""Naseeb Mind link endpoints (/api/mind-link/): student side (JWT) and Mind's signed calls."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User
from apps.users.throttles import IPCeilingThrottle, ScopedRateThrottle

from .. import mind_link
from ..models import StudentProfile


class MindLinkSignedThrottle(IPCeilingThrottle):
    scope = 'mind_link_signed'


class MindLinkErrorMixin:
    def handle_exception(self, exc):
        if isinstance(exc, mind_link.MindLinkError):
            return Response({'code': exc.code}, status=exc.status)
        return super().handle_exception(exc)


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.STUDENT)


def _student(request):
    student = StudentProfile.objects.filter(user=request.user).first()
    if student is None:
        raise mind_link.MindLinkError('no_student_profile', 403)
    return student


class MindLinkView(MindLinkErrorMixin, APIView):
    """Status (GET) and stop sharing (DELETE) for the signed-in student."""

    permission_classes = [IsStudent]

    def get(self, request):
        return Response(mind_link.status_for(_student(request)))

    def delete(self, request):
        mind_link.unlink_student(_student(request))
        return Response(mind_link.status_for(_student(request)))


class MindLinkStartView(MindLinkErrorMixin, APIView):
    permission_classes = [IsStudent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'mind_link_start'

    def post(self, request):
        lang = request.data.get('lang') if hasattr(request.data, 'get') else None
        return Response(mind_link.start(_student(request), lang))


class SignedMindView(MindLinkErrorMixin, APIView):
    """Server-to-server: no session, no CSRF (APIView is exempt), the HMAC is the credential."""

    authentication_classes = []
    permission_classes = []
    throttle_classes = [MindLinkSignedThrottle]
    handler = None

    def post(self, request):
        # The raw body is read before anything parses it: the signature covers those exact bytes.
        data = mind_link.parse_body(mind_link.verify_request(request))
        return Response(type(self).handler(data))


class MindLinkCompleteView(SignedMindView):
    handler = staticmethod(mind_link.complete)


class MindLinkSyncView(SignedMindView):
    handler = staticmethod(mind_link.sync)


class MindLinkUnlinkView(SignedMindView):
    handler = staticmethod(mind_link.unlink_mind)
