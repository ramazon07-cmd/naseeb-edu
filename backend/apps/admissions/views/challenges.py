"""Admissions API views — challenges."""
from django.db import IntegrityError, transaction
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from apps.users.models import User
from ..models import ChallengeAttempt, StudentProfile
from ..serializers import ChallengeAttemptSerializer
from ..params import int_param
from ..scoping import scope_students


class ChallengeAttemptPermission(permissions.BasePermission):
    """Deliberately narrower than CounselorOrOwnerPermission.

    A personality profile is not the same kind of record as a task list. The
    shared permission lets a school-account holder read anything with a student
    FK, which here would hand an administrator every student's trait scores --
    the class-ranked-by-conscientiousness list this product must never produce.

    So: a student reads and writes their own attempts; their ASSIGNED counselor
    reads them; nobody else, including other counselors at the same school and
    including teachers. Nobody but the student may create one, and no one at all
    may edit or delete one -- the record belongs to the student and is not
    something staff can quietly correct.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if view.action in {'update', 'partial_update', 'destroy'}:
            return False
        if view.action == 'create':
            return user.role == User.Role.STUDENT
        return user.role == User.Role.STUDENT or user.is_counselor_like

    def has_object_permission(self, request, view, obj):
        if request.method not in permissions.SAFE_METHODS:
            return False
        user = request.user
        if obj.student.user_id == user.id:
            return True
        if user.role == User.Role.ADMIN or user.is_superuser:
            return True
        return user.is_counselor_like and obj.student.assigned_counselor_id == user.id


class ChallengeAttemptViewSet(viewsets.ModelViewSet):
    serializer_class = ChallengeAttemptSerializer
    permission_classes = [ChallengeAttemptPermission]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        queryset = ChallengeAttempt.objects.select_related('student__user')
        if user.role == User.Role.STUDENT:
            return queryset.filter(student__user=user)
        if user.is_counselor_like:
            queryset = scope_students(queryset, user, via='student')
        else:
            return queryset.none()
        student = int_param(self.request.query_params, 'student')
        return queryset.filter(student_id=student) if student else queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = StudentProfile.objects.filter(user=request.user).first()
        if student is None:
            raise PermissionDenied('Finish creating your student profile first.')
        # Saving is idempotent on (challenge, completed_at): the client retries
        # an unconfirmed save with the same timestamp, and gets the stored row back.
        completed_at = serializer.validated_data.get('completed_at')
        if completed_at is not None:
            existing = self._existing(student, serializer.validated_data['challenge'], completed_at)
            if existing is not None:
                return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        try:
            with transaction.atomic():
                serializer.save(student=student)
        except IntegrityError:
            existing = self._existing(student, serializer.validated_data['challenge'], completed_at)
            if existing is None:
                raise
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _existing(student, challenge, completed_at):
        if completed_at is None:
            return None
        return (ChallengeAttempt.objects.select_related('student__user')
                .filter(student=student, challenge=challenge, completed_at=completed_at).first())
