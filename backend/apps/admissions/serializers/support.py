"""Admissions API serializers — support."""
from rest_framework import serializers
from apps.users.models import User
from ..models import SupportTicket


class SupportTicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    requester_role = serializers.CharField(source='requester.role', read_only=True)
    responded_by_name = serializers.SerializerMethodField()
    has_unread_response = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportTicket
        fields = (
            'id', 'requester', 'requester_name', 'requester_role', 'category',
            'subject', 'message', 'status', 'admin_response', 'responded_by',
            'responded_by_name', 'responded_at', 'requester_viewed_at',
            'has_unread_response', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'requester', 'responded_by', 'responded_by_name', 'responded_at',
            'requester_viewed_at', 'has_unread_response', 'created_at', 'updated_at',
        )

    def get_requester_name(self, obj):
        return obj.requester.get_full_name() or obj.requester.username

    def get_responded_by_name(self, obj):
        if not obj.responded_by:
            return None
        return obj.responded_by.get_full_name() or obj.responded_by.username

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_product_admin = bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.role == User.Role.ADMIN)
        )
        if not is_product_admin and {'status', 'admin_response'}.intersection(self.initial_data):
            raise serializers.ValidationError('Only an admin can set ticket status or support response.')
        return attrs
