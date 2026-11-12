"""The website's side of a student's Telegram link (signed-in student, JWT)."""
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import student_link
from .services import Refused


class StudentTelegramView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'telegram_link'

    def get_throttles(self):
        # Only typing a code is limited: six digits must not be guessable.
        return [ScopedRateThrottle()] if self.request.method == 'POST' else []

    def handle_exception(self, exc):
        if isinstance(exc, Refused):
            return Response({'code': exc.code, **exc.extra}, status=exc.status)
        return super().handle_exception(exc)

    def get(self, request):
        return Response(student_link.link_status(request.user))

    def post(self, request):
        code = request.data.get('code') if hasattr(request.data, 'get') else None
        return Response(student_link.link_code(request.user, code))

    def delete(self, request):
        return Response(student_link.unlink(request.user))
