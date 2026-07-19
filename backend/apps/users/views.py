from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import User
from .serializers import RegisterSerializer, UserSerializer


class IsRoleScopedUserAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_counselor_like:
            return True
        if view.action == 'create':
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_counselor_like:
            return True
        if request.user.is_organization:
            return (
                request.user.school_id is not None
                and obj.role == User.Role.STUDENT
                and obj.school_id == request.user.school_id
            )
        return obj == request.user


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoleScopedUserAccess]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == User.Role.ADMIN:
            return User.objects.all().order_by('first_name', 'last_name')
        if user.role == User.Role.COUNSELOR:
            return User.objects.filter(role__in=[User.Role.STUDENT, User.Role.COUNSELOR]).order_by('first_name')
        if user.role == User.Role.ORGANIZATION:
            if not user.school_id:
                return User.objects.none()
            return User.objects.filter(role=User.Role.STUDENT, school=user.school).order_by('first_name', 'last_name')
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)
