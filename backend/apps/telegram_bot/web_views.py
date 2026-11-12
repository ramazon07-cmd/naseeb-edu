"""The website's side of Telegram: a student's link, and the counselor allowlist (superadmin, JWT)."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.users.models import User

from . import staff_access, student_link
from .services import Refused


class RefusedMixin:
    def handle_exception(self, exc):
        if isinstance(exc, Refused):
            return Response({'code': exc.code, **exc.extra}, status=exc.status)
        return super().handle_exception(exc)


class StudentTelegramView(RefusedMixin, APIView):
    """Status (GET) and disconnect (DELETE) of the signed-in student's Telegram."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'telegram_link'

    def get_throttles(self):
        # Polling while the student presses Start in Telegram must not hit the hourly link limit.
        return [] if self.request.method == 'GET' else super().get_throttles()

    def get(self, request):
        return Response(student_link.link_status(request.user))

    def delete(self, request):
        return Response(student_link.unlink(request.user))


class StudentTelegramLinkView(RefusedMixin, APIView):
    """A one-time bot link for the signed-in student; opening it and pressing Start links their chat."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'telegram_link'

    def post(self, request):
        return Response(student_link.issue_token(request.user))


class IsSuperadmin(permissions.BasePermission):
    """Product admins of the superadmin tier (is_superuser, or role admin without a lower tier)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_product_admin and user.staff_tier == User.AdminTier.SUPERADMIN)


class StaffAccessListView(RefusedMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperadmin]

    def get(self, request):
        return Response({'results': staff_access.list_access()})


class StaffAccessDetailView(RefusedMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperadmin]

    def get(self, request, user_id):
        return Response(staff_access.get_access(user_id))

    def put(self, request, user_id):
        data = request.data if hasattr(request.data, 'get') else {}
        payload, _ = staff_access.set_access(user_id, data.get('telegram_username'), request.user)
        return Response(payload)

    def delete(self, request, user_id):
        staff_access.clear_access(user_id)
        return Response(status=204)
