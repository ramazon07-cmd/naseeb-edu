"""Admissions API views — support."""
from django.utils import timezone
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.users.models import User
from ..models import SupportTicket
from ..listing import ListQueryMixin
from ..serializers import SupportTicketSerializer


class SupportTicketPermission(permissions.BasePermission):
    allowed_roles = {
        User.Role.ADMIN,
        User.Role.COUNSELOR,
        User.Role.ORGANIZATION,
        User.Role.STUDENT,
    }

    @staticmethod
    def is_product_admin(user):
        return bool(user.is_superuser or user.role == User.Role.ADMIN)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or user.role not in self.allowed_roles:
            return False
        if view.action in {'update', 'partial_update'}:
            return self.is_product_admin(user)
        return True

    def has_object_permission(self, request, view, obj):
        if self.is_product_admin(request.user):
            return True
        if obj.requester_id != request.user.id:
            return False
        return request.method in permissions.SAFE_METHODS or view.action == 'mark_viewed'


class SupportTicketViewSet(
    ListQueryMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SupportTicketSerializer
    permission_classes = [SupportTicketPermission]
    queryset = SupportTicket.objects.select_related('requester', 'responded_by').all()
    search_fields = ('subject',)
    choice_filters = {
        'status': ('status', SupportTicket.Status.choices),
        'category': ('category', SupportTicket.Category.choices),
    }
    int_filters = {'requester': 'requester_id'}
    date_filters = {'created': 'created_at', 'updated': 'updated_at'}
    ordering_options = {'-updated': ('-updated_at', '-id'), '-created': ('-created_at', '-id')}
    default_cursor_ordering = '-updated'

    def get_queryset(self):
        user = self.request.user
        if SupportTicketPermission.is_product_admin(user):
            return self.queryset
        return self.queryset.filter(requester=user)

    def perform_create(self, serializer):
        serializer.save(
            requester=self.request.user,
            status=SupportTicket.Status.OPEN,
            admin_response='',
        )

    def perform_update(self, serializer):
        previous_response = serializer.instance.admin_response
        ticket = serializer.save()
        if ticket.admin_response and ticket.admin_response != previous_response:
            ticket.responded_by = self.request.user
            ticket.responded_at = timezone.now()
            ticket.requester_viewed_at = None
            ticket.save(update_fields=[
                'responded_by', 'responded_at', 'requester_viewed_at', 'updated_at',
            ])

    @action(detail=True, methods=['post'], url_path='mark-viewed')
    def mark_viewed(self, request, pk=None):
        ticket = self.get_object()
        if ticket.requester_id != request.user.id:
            return Response(
                {'detail': 'Only the ticket requester can mark a response as viewed.'},
                status=403,
            )
        if ticket.responded_at:
            ticket.requester_viewed_at = timezone.now()
            ticket.save(update_fields=['requester_viewed_at', 'updated_at'])
        return Response(self.get_serializer(ticket).data)
