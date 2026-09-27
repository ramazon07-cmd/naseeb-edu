"""Admissions API serializers — messaging."""
from rest_framework import serializers
from django.utils import timezone
from apps.users.serializers import ContactSerializer
from ..scoping import tenant_school_id
from .common import scope_related_field
from ..models import (
    ChannelMembership,
    ChannelMessage,
    MessageChannel,
    MessageReport,
)

UNAVAILABLE_CHANNEL = 'Join the channel before posting.'
UNAVAILABLE_PARENT = 'Reply to a message in one of your channels.'


class ChannelMembershipSerializer(serializers.ModelSerializer):
    user_detail = ContactSerializer(source='user', read_only=True)

    class Meta:
        model = ChannelMembership
        fields = ('id', 'channel', 'user', 'user_detail', 'role', 'joined_at', 'last_read_at', 'notifications_enabled', 'muted_until')
        read_only_fields = ('channel', 'joined_at', 'last_read_at', 'muted_until')


class MessageChannelSerializer(serializers.ModelSerializer):
    is_saved_messages = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    members_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = MessageChannel
        fields = (
            'id', 'kind', 'name', 'display_name', 'description', 'school', 'school_name',
            'created_by', 'is_public', 'is_global', 'is_archived', 'last_message_at', 'members_count',
            'is_member', 'my_role', 'unread_count', 'last_message', 'created_at', 'updated_at', 'is_saved_messages',
        )
        read_only_fields = ('created_by', 'last_message_at')

    @staticmethod
    def _prefetched_memberships(obj):
        # discoverable_channels_for() loads the requester's membership and both
        # members of direct chats; other callers may prefetch all of them.
        listed = getattr(obj, 'listed_memberships', None)
        if listed is not None:
            return listed
        return getattr(obj, '_prefetched_objects_cache', {}).get('memberships')

    def get_members_count(self, obj) -> int:
        total = getattr(obj, 'members_total', None)
        return obj.memberships.count() if total is None else total

    def _membership(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        cached = getattr(obj, '_current_membership', None)
        if cached is not None:
            return cached
        prefetched = self._prefetched_memberships(obj)
        if prefetched is not None:
            return next((membership for membership in prefetched if membership.user_id == request.user.id), None)
        return obj.memberships.filter(user=request.user).first()

    def get_is_saved_messages(self, obj):
        return obj.kind == MessageChannel.Kind.DIRECT and bool(obj.direct_key and obj.direct_key.startswith('saved:'))

    def get_display_name(self, obj):
        request = self.context.get('request')
        if obj.kind == MessageChannel.Kind.DIRECT and request and request.user.is_authenticated:
            prefetched = self._prefetched_memberships(obj)
            other = next((membership for membership in prefetched or [] if membership.user_id != request.user.id), None)
            if prefetched is None:
                other = obj.memberships.exclude(user=request.user).select_related('user').first()
            if other:
                return other.user.get_full_name() or other.user.username
        return obj.name or obj.get_kind_display()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            immutable = {'kind', 'school', 'is_public', 'is_global'} & set(attrs)
            if immutable:
                raise serializers.ValidationError({
                    field: 'This channel setting cannot be changed after creation.'
                    for field in sorted(immutable)
                })
        return attrs

    def get_is_member(self, obj):
        return self._membership(obj) is not None

    def get_my_role(self, obj):
        membership = self._membership(obj)
        return membership.role if membership else None

    def get_unread_count(self, obj) -> int:
        if hasattr(obj, '_unread_count'):
            return obj._unread_count
        request = self.context.get('request')
        membership = self._membership(obj)
        if not request or not membership:
            return 0
        messages = obj.messages.filter(deleted_at__isnull=True).exclude(sender=request.user)
        if membership.last_read_at:
            messages = messages.filter(created_at__gt=membership.last_read_at)
        return messages.count()

    def get_last_message(self, obj):
        request = self.context.get('request')
        if hasattr(obj, '_last_message'):
            message = obj._last_message
        else:
            message = obj.messages.select_related('sender').order_by('-created_at', '-id').first()
        if not message:
            return None
        can_reveal = bool(
            request
            and request.user.is_authenticated
            and message.sender_id == request.user.id
        )
        anonymous = message.is_anonymous and not can_reveal
        sender_name = 'Deleted user'
        if message.sender:
            sender_name = message.sender.get_full_name() or message.sender.username
        return {
            'body': 'Message deleted' if message.deleted_at else message.body[:160],
            'sender_name': 'Anonymous' if anonymous else sender_name,
            'created_at': message.created_at,
        }


class ChannelMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()
    parent_preview = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    is_reported_by_me = serializers.SerializerMethodField()

    class Meta:
        model = ChannelMessage
        fields = (
            'id', 'channel', 'sender_id', 'sender_name', 'parent', 'parent_preview',
            'replies_count', 'body', 'is_anonymous', 'is_edited', 'is_accepted_answer',
            'is_reported_by_me', 'deleted_at', 'created_at', 'updated_at',
        )
        read_only_fields = ('sender_id', 'sender_name', 'is_edited', 'is_accepted_answer', 'deleted_at')

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        # Posting needs membership, so a channel (or a message to reply to)
        # outside the caller's own channels fails like a missing id.
        member_channels = (
            MessageChannel.objects.filter(memberships__user=user)
            if user is not None and user.is_authenticated else MessageChannel.objects.none()
        )
        scope_related_field(fields['channel'], member_channels, UNAVAILABLE_CHANNEL)
        scope_related_field(
            fields['parent'], ChannelMessage.objects.filter(channel__in=member_channels), UNAVAILABLE_PARENT,
        )
        return fields

    def _can_reveal_sender(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.sender_id == request.user.id

    def get_sender_id(self, obj):
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return None
        return obj.sender_id

    def get_sender_name(self, obj):
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return 'Anonymous'
        if not obj.sender:
            return 'Deleted user'
        return obj.sender.get_full_name() or obj.sender.username

    def get_parent_preview(self, obj):
        if not obj.parent:
            return None
        return {'id': obj.parent_id, 'body': obj.parent.body[:120]}

    def get_replies_count(self, obj) -> int:
        annotated = getattr(obj, 'replies_total', None)
        return obj.replies.count() if annotated is None else annotated

    def get_is_reported_by_me(self, obj) -> bool:
        annotated = getattr(obj, 'reported_by_me', None)
        if annotated is not None:
            return annotated
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reports.filter(reporter=request.user).exists()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if self.instance:
            forbidden = set(attrs) - {'body', 'is_anonymous'}
            if forbidden:
                raise serializers.ValidationError({
                    field: 'This field cannot be changed after posting.' for field in sorted(forbidden)
                })
        channel = attrs.get('channel', getattr(self.instance, 'channel', None))
        if request and channel:
            if channel.is_archived:
                raise serializers.ValidationError('This channel is archived.')
            membership = channel.memberships.filter(user=request.user).first()
            if not membership:
                raise serializers.ValidationError('Join the channel before posting.')
            if not self.instance and membership.muted_until and membership.muted_until > timezone.now():
                raise serializers.ValidationError({
                    'channel': f'You are muted in this channel until {membership.muted_until.isoformat()}.'
                })
            is_anonymous = attrs.get('is_anonymous', getattr(self.instance, 'is_anonymous', False))
            if is_anonymous and channel.kind not in {
                MessageChannel.Kind.COMMUNITY,
                MessageChannel.Kind.DISCUSSION,
            }:
                raise serializers.ValidationError({'is_anonymous': 'Anonymous mode is only available in Community and Discussions.'})
            parent = attrs.get('parent')
            if parent and parent.channel_id != channel.id:
                raise serializers.ValidationError({'parent': 'Reply must belong to the same channel.'})
        return attrs


class MessageReportSerializer(serializers.ModelSerializer):
    channel_id = serializers.IntegerField(source='message.channel_id', read_only=True)
    channel_name = serializers.SerializerMethodField()
    message_body = serializers.SerializerMethodField()
    message_is_anonymous = serializers.BooleanField(source='message.is_anonymous', read_only=True)
    message_deleted_at = serializers.DateTimeField(source='message.deleted_at', read_only=True)
    sender_id = serializers.IntegerField(source='message.sender_id', read_only=True)
    sender_name = serializers.SerializerMethodField()
    reporter_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MessageReport
        fields = (
            'id', 'message', 'channel_id', 'channel_name', 'message_body',
            'message_is_anonymous', 'message_deleted_at', 'sender_id', 'sender_name',
            'reporter', 'reporter_name', 'reason', 'details', 'status', 'action',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'moderator_note',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def _reveals(self, person):
        """Moderators see identities only of people from their own school.

        A moderator of a global channel therefore never learns who reported,
        or who wrote anonymously, from another school.
        """
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if viewer is None or not viewer.is_authenticated:
            return False
        if viewer.is_product_admin or person is None or person.pk == viewer.pk:
            return True
        viewer_school = tenant_school_id(viewer)
        return bool(viewer_school and tenant_school_id(person) == viewer_school)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._reveals(instance.reporter):
            data['reporter'] = None
            data['reporter_name'] = 'Hidden reporter'
        message = instance.message
        if message.is_anonymous and not self._reveals(message.sender):
            data['sender_id'] = None
            data['sender_name'] = 'Anonymous'
        return data

    def get_channel_name(self, obj):
        return obj.message.channel.name or obj.message.channel.get_kind_display()

    def get_message_body(self, obj):
        return 'Message deleted' if obj.message.deleted_at else obj.message.body

    def get_sender_name(self, obj):
        sender = obj.message.sender
        if not sender:
            return 'Deleted user'
        return sender.get_full_name() or sender.username

    def get_reporter_name(self, obj):
        return obj.reporter.get_full_name() or obj.reporter.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
