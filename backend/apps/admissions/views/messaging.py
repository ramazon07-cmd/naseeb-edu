"""Admissions API views — messaging."""
import hashlib
from datetime import timedelta
from django.db import transaction
from django.db.models import (
    Count,
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import get_language
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from apps.users.models import User
from apps.users.serializers import ContactSerializer
from core.pagination import BoundedCountPaginator, keyset_filter
from ..models import (
    ChannelMembership,
    ChannelMessage,
    MessageChannel,
    MessageReport,
    ParentStudentLink,
    StudentProfile,
)
from ..serializers import (
    ChannelMembershipSerializer,
    ChannelMessageSerializer,
    MessageChannelSerializer,
    MessageReportSerializer,
)
from ..params import int_list_param, int_param
from ..scoping import scope_students, student_lookups, tenant_school, tenant_school_id
from .common import CONTACT_LIST_LIMIT


STAFF_ROLES = (User.Role.ORGANIZATION, User.Role.TEACHER, User.Role.COUNSELOR)


def messaging_contacts_for(user):
    """People ``user`` may message: always inside their own school.

    Students are matched by their profile's school through the canonical
    scoping rules, so a counselor reaches only students assigned to them in
    their own school, and nobody reaches a school they left.
    """
    queryset = User.objects.filter(is_active=True).exclude(id=user.id)
    order = ('first_name', 'last_name', 'username')
    if user.is_product_admin:
        return queryset.order_by(*order)
    if user.role == User.Role.PARENT:
        # Only the counselors of children whose link the parent accepted, and
        # only while the counselor serves that child in the child's school.
        counselor_ids = StudentProfile.objects.filter(
            parent_links__parent=user,
            parent_links__status=ParentStudentLink.Status.ACTIVE,
            assigned_counselor__school_id=F('school_id'),
            school__is_active=True,
        ).values('assigned_counselor_id')
        return queryset.filter(id__in=counselor_ids, role=User.Role.COUNSELOR).order_by(*order)
    school_id = tenant_school_id(user)
    if not school_id:
        return queryset.none()
    school_staff = Q(school_id=school_id, role__in=STAFF_ROLES)
    if user.role == User.Role.STUDENT:
        return queryset.filter(school_staff).order_by(*order)
    if user.role not in STAFF_ROLES:
        return queryset.none()
    lookups = student_lookups(user)
    if not lookups:
        return queryset.none()
    students = Q(role=User.Role.STUDENT, **{f'student_profile__{key}': value for key, value in lookups.items()})
    reachable = students | school_staff
    if user.role == User.Role.COUNSELOR:
        reachable |= Q(role=User.Role.PARENT, id__in=scope_students(
            ParentStudentLink.objects.filter(status=ParentStudentLink.Status.ACTIVE), user, via='student',
        ).values('parent_id'))
    return queryset.filter(reachable).order_by(*order)


def discoverable_channels_for(user):
    # Only the requester's own membership is loaded, plus both members of direct
    # chats (for the display name); a community channel can have thousands.
    listed_memberships = ChannelMembership.objects.filter(
        Q(user=user) | Q(channel__kind=MessageChannel.Kind.DIRECT),
    ).select_related('user')
    queryset = MessageChannel.objects.select_related('school', 'created_by').annotate(
        members_total=Coalesce(
            Subquery(
                ChannelMembership.objects.filter(channel=OuterRef('pk')).order_by()
                .values('channel').annotate(total=Count('id')).values('total'),
            ),
            0,
        ),
    ).prefetch_related(Prefetch('memberships', queryset=listed_memberships, to_attr='listed_memberships'))
    if user.is_product_admin:
        return queryset
    own_channels = Q(id__in=ChannelMembership.objects.filter(user=user).values('channel_id'))
    if user.role == User.Role.PARENT:
        return queryset.filter(own_channels)
    # Subqueries instead of joins: joining memberships (or a counselor's
    # students) repeats each channel once per matching row and needs DISTINCT.
    # A channel without a school is open to everyone only when a product
    # admin created it as global; otherwise only its members see it.
    visible = own_channels | Q(is_public=True, is_global=True)
    school_id = tenant_school_id(user)
    if school_id:
        visible |= Q(is_public=True, school_id=school_id)
    return queryset.filter(visible)


def unread_channel_messages(user):
    """Messages from others in ``user``'s channels posted after they last read it."""
    # One filter() call so the membership join is shared by both conditions.
    return ChannelMessage.objects.filter(
        Q(channel__memberships__last_read_at__isnull=True)
        | Q(created_at__gt=F('channel__memberships__last_read_at')),
        deleted_at__isnull=True,
        channel__memberships__user=user,
    ).exclude(sender=user)


def attach_channel_summaries(channels, user):
    """Bulk-load unread counts and last messages for a page of channels (2 queries)."""
    channels = list(channels)
    if not channels:
        return channels
    ids = [channel.id for channel in channels]
    unread = dict(
        unread_channel_messages(user).filter(channel_id__in=ids)
        .order_by().values('channel_id').annotate(total=Count('id')).values_list('channel_id', 'total')
    )
    latest_ids = ChannelMessage.objects.filter(channel_id=OuterRef('pk')).order_by('-created_at', '-id').values('id')[:1]
    last_ids = dict(
        MessageChannel.objects.filter(id__in=ids).annotate(last_id=Subquery(latest_ids)).values_list('id', 'last_id')
    )
    messages = ChannelMessage.objects.select_related('sender').in_bulk([mid for mid in last_ids.values() if mid])
    for channel in channels:
        channel._unread_count = unread.get(channel.id, 0)
        channel._last_message = messages.get(last_ids.get(channel.id))
    return channels


def moderatable_channels_for(user):
    queryset = MessageChannel.objects.select_related('school', 'created_by')
    if user.is_superuser or user.role == User.Role.ADMIN:
        return queryset
    if user.role not in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
        return queryset.none()
    moderator_memberships = Q(
        memberships__user=user,
        memberships__role__in=[ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR],
    )
    return queryset.filter(moderator_memberships).distinct()


def channel_membership_role(channel, user):
    membership = channel.memberships.filter(user=user).first()
    return membership.role if membership else None


MODERATOR_ROLES = {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR}


def can_accept_answer(channel, user, role):
    """Discussion owner or moderators; school staff only inside their own school.

    A global discussion has no school, so staff rank alone never reaches it.
    """
    if user.is_product_admin or channel.created_by_id == user.id or role in MODERATOR_ROLES:
        return True
    return bool(
        user.is_task_manager
        and channel.school_id
        and channel.school_id == tenant_school_id(user)
    )


class MessageChannelPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            return True
        role = channel_membership_role(obj, user)
        if request.method in permissions.SAFE_METHODS:
            return bool(role or obj.is_public)
        if view.action in {'join'}:
            return obj.is_public
        if view.action in {'mark_read', 'leave'}:
            return bool(role)
        return role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR}


class MessageChannelViewSet(viewsets.ModelViewSet):
    serializer_class = MessageChannelSerializer
    permission_classes = [MessageChannelPermission]
    queryset = MessageChannel.objects.all()

    def get_queryset(self):
        queryset = discoverable_channels_for(self.request.user)
        kind = self.request.query_params.get('kind')
        search = self.request.query_params.get('search')
        if kind:
            queryset = queryset.filter(kind=kind)
        if search:
            matching_users = User.objects.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(username__icontains=search)
            ).exclude(pk=self.request.user.pk)
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
                | Q(kind=MessageChannel.Kind.DIRECT, memberships__user__in=matching_users)
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        kind = serializer.validated_data['kind']
        if kind == MessageChannel.Kind.DIRECT:
            raise drf_serializers.ValidationError({'kind': 'Use the direct action to open a direct conversation.'})
        if kind in {MessageChannel.Kind.GROUP, MessageChannel.Kind.COMMUNITY} and not (
            user.is_task_manager or user.is_organization
        ):
            raise drf_serializers.ValidationError({'kind': 'Only school staff can create Group or Community channels.'})
        if kind in {MessageChannel.Kind.GROUP, MessageChannel.Kind.COMMUNITY, MessageChannel.Kind.DISCUSSION} and not serializer.validated_data.get('name'):
            raise drf_serializers.ValidationError({'name': 'A channel name or discussion title is required.'})

        is_public = kind in {MessageChannel.Kind.COMMUNITY, MessageChannel.Kind.DISCUSSION}
        is_global = bool(serializer.validated_data.get('is_global'))
        if is_global:
            if not user.is_product_admin:
                raise PermissionDenied('Only a product admin can create a channel for every school.')
            if not is_public:
                raise drf_serializers.ValidationError({'is_global': 'Only communities and discussions can be global.'})
            school = None
        else:
            school = self.permitted_channel_school(serializer.validated_data.get('school'))
        requested_members = int_list_param(self.request.data, 'members')
        with transaction.atomic():
            channel = serializer.save(created_by=user, school=school, is_public=is_public, is_global=is_global)
            ChannelMembership.objects.create(channel=channel, user=user, role=ChannelMembership.Role.OWNER)
            allowed_ids = set(
                messaging_contacts_for(user).filter(id__in=requested_members).values_list('id', flat=True)
            )
            ChannelMembership.objects.bulk_create([
                ChannelMembership(channel=channel, user_id=user_id)
                for user_id in allowed_ids
            ], ignore_conflicts=True)

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        if page is not None:
            attach_channel_summaries(page, self.request.user)
        return page

    def permitted_channel_school(self, school):
        """Every non-admin channel lives in the creator's own school.

        Without a school there is no tenant to hold the channel, so such
        users (parents included) cannot create one.
        """
        user = self.request.user
        if user.is_product_admin:
            return school or user.school
        own_school = tenant_school(user)
        if own_school is None:
            raise PermissionDenied('Only members of a school can create channels.')
        if school is not None and school.pk != own_school.pk:
            raise drf_serializers.ValidationError({'school': 'You can only create channels in your own school.'})
        return own_school

    @action(detail=False, methods=['get'])
    def contacts(self, request):
        contacts = messaging_contacts_for(request.user).select_related('school')
        search = request.query_params.get('search', '').strip()
        if search:
            contacts = contacts.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(username__icontains=search)
            )
        # A product admin's contact scope is every user; cap the picker.
        return Response(ContactSerializer(
            contacts[:CONTACT_LIST_LIMIT], many=True, context={'request': request},
        ).data)

    @action(detail=False, methods=['get'])
    def overview(self, request):
        channels = discoverable_channels_for(request.user)
        counts = {kind: 0 for kind, _ in MessageChannel.Kind.choices}
        counts.update(dict(
            channels.order_by().values('kind').annotate(total=Count('id')).values_list('kind', 'total')
        ))
        memberships = ChannelMembership.objects.filter(
            user=request.user,
            channel__in=channels,
        ).annotate(
            unread=Count(
                'channel__messages',
                filter=(
                    Q(channel__messages__deleted_at__isnull=True)
                    & ~Q(channel__messages__sender=request.user)
                    & (
                        Q(last_read_at__isnull=True)
                        | Q(channel__messages__created_at__gt=F('last_read_at'))
                    )
                ),
            ),
        )
        contacts = messaging_contacts_for(request.user)
        can_moderate = bool(request.user.is_task_manager or request.user.is_organization)
        pending_reports = 0
        if can_moderate:
            pending_reports = MessageReport.objects.filter(
                message__channel__in=moderatable_channels_for(request.user),
                status__in=[MessageReport.Status.PENDING, MessageReport.Status.REVIEWING],
            ).count()
        return Response({
            'channel_counts': counts,
            'unread_total': sum(membership.unread for membership in memberships),
            'contacts_total': contacts.count(),
            'students_total': contacts.filter(role=User.Role.STUDENT).count(),
            'staff_total': contacts.exclude(role=User.Role.STUDENT).count(),
            'pending_reports': pending_reports,
            'can_moderate': can_moderate,
        })

    @action(detail=False, methods=['post'])
    def saved(self, request):
        with transaction.atomic():
            channel, created = MessageChannel.objects.get_or_create(
                direct_key=f'saved:{request.user.pk}',
                defaults={
                    'kind': MessageChannel.Kind.DIRECT,
                    'name': 'Saved Messages',
                    'created_by': request.user,
                    'is_public': False,
                },
            )
            ChannelMembership.objects.get_or_create(
                channel=channel, user=request.user,
                defaults={'role': ChannelMembership.Role.OWNER},
            )
        return Response(self.get_serializer(channel).data, status=201 if created else 200)

    @action(detail=False, methods=['post'])
    def direct(self, request):
        target_id = int_param(request.data, 'user')
        target = messaging_contacts_for(request.user).filter(id=target_id).first()
        if not target:
            return Response({'detail': 'This user is not available as a direct-message contact.'}, status=403)
        first_id, second_id = sorted([request.user.id, target.id])
        direct_key = f'{first_id}:{second_id}'
        with transaction.atomic():
            channel, created = MessageChannel.objects.get_or_create(
                direct_key=direct_key,
                defaults={
                    'kind': MessageChannel.Kind.DIRECT,
                    'created_by': request.user,
                    'school': request.user.school or target.school,
                    'is_public': False,
                },
            )
            if created or channel.is_archived:
                # A conversation archived when someone changed school reopens
                # only because both people are valid contacts again.
                channel.school = (
                    request.user.student_profile.school
                    if request.user.role == User.Role.STUDENT and hasattr(request.user, 'student_profile')
                    else request.user.school or target.school
                )
                channel.is_archived = False
                channel.save(update_fields=['school', 'is_archived', 'updated_at'])
            ChannelMembership.objects.bulk_create([
                ChannelMembership(channel=channel, user=request.user, role=ChannelMembership.Role.OWNER),
                ChannelMembership(channel=channel, user=target, role=ChannelMembership.Role.MEMBER),
            ], ignore_conflicts=True)
        return Response(MessageChannelSerializer(channel, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        channel = self.get_object()
        if request.user.role == User.Role.PARENT:
            return Response({'detail': 'Parent accounts cannot join community channels.'}, status=403)
        if not channel.is_public:
            return Response({'detail': 'This channel is invite-only.'}, status=403)
        membership, created = ChannelMembership.objects.get_or_create(channel=channel, user=request.user)
        return Response(ChannelMembershipSerializer(membership, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        channel = self.get_object()
        if channel.kind == MessageChannel.Kind.DIRECT:
            return Response({'detail': 'Direct conversations cannot be left.'}, status=400)
        membership = channel.memberships.filter(user=request.user).first()
        if membership and membership.role == ChannelMembership.Role.OWNER and channel.memberships.filter(role=ChannelMembership.Role.OWNER).count() == 1:
            return Response({'detail': 'Assign another owner before leaving.'}, status=400)
        if membership:
            membership.delete()
        return Response(status=204)

    @action(detail=True, methods=['get', 'post', 'delete'])
    def members(self, request, pk=None):
        channel = self.get_object()
        membership_role = channel_membership_role(channel, request.user)
        # Staff rank is no key to a channel: only its own moderators manage it.
        can_manage = request.user.is_product_admin or membership_role in MODERATOR_ROLES
        if request.method == 'GET':
            if not (membership_role or request.user.is_product_admin):
                return Response({'detail': 'Join the channel before viewing its members.'}, status=403)
            return Response(ChannelMembershipSerializer(
                channel.memberships.select_related('user').all(),
                many=True,
                context={'request': request},
            ).data)
        if channel.kind == MessageChannel.Kind.DIRECT:
            return Response({'detail': 'Direct conversation participants cannot be changed.'}, status=400)
        if not can_manage:
            return Response({'detail': 'Only channel moderators can manage members.'}, status=403)
        if request.method == 'DELETE':
            target_membership = channel.memberships.filter(user_id=int_param(request.data, 'user')).first()
            if not target_membership:
                return Response(status=204)
            if target_membership.role == ChannelMembership.Role.OWNER:
                return Response({'detail': 'Channel owners cannot be removed.'}, status=400)
            target_membership.delete()
            return Response(status=204)
        target = messaging_contacts_for(request.user).filter(id=int_param(request.data, 'user')).first()
        if not target:
            return Response({'detail': 'This user is not available for this channel.'}, status=403)
        requested_role = request.data.get('role', ChannelMembership.Role.MEMBER)
        if requested_role not in {ChannelMembership.Role.MEMBER, ChannelMembership.Role.MODERATOR}:
            return Response({'detail': 'Members can only be added as member or moderator.'}, status=400)
        membership, created = ChannelMembership.objects.get_or_create(
            channel=channel,
            user=target,
            defaults={'role': requested_role},
        )
        if not created and membership.role != ChannelMembership.Role.OWNER and membership.role != requested_role:
            membership.role = requested_role
            membership.save(update_fields=['role'])
        return Response(ChannelMembershipSerializer(membership, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        channel = self.get_object()
        membership = channel.memberships.filter(user=request.user).first()
        if not membership:
            return Response({'detail': 'Join the channel before marking it read.'}, status=403)
        membership.last_read_at = timezone.now()
        membership.save(update_fields=['last_read_at'])
        return Response({'status': 'read', 'channel': channel.id})


class ChannelMessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100
    # A long-lived community channel must not cost a full COUNT per page.
    django_paginator_class = BoundedCountPaginator


# Newest first; ?before=<message id> continues from that message (a keyset
# cursor), so older pages stay stable while new messages arrive.
MESSAGE_TIMELINE = ('-created_at', '-id')


class ChannelMessagePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if view.action in {'update', 'partial_update'}:
            # Only the author may edit: the message keeps showing the author's
            # name, so nobody else (moderators and admins included) may change it.
            return obj.sender_id == user.id
        if user.is_product_admin:
            return True
        role = channel_membership_role(obj.channel, user)
        if request.method in permissions.SAFE_METHODS:
            return bool(role or obj.channel.is_public)
        if view.action == 'accept':
            return can_accept_answer(obj.channel, user, role)
        if view.action == 'destroy':
            return bool(obj.sender_id == user.id or role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR})
        return bool(role)


class ChannelMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelMessageSerializer
    permission_classes = [ChannelMessagePermission]
    pagination_class = ChannelMessagePagination
    queryset = ChannelMessage.objects.select_related('channel', 'sender', 'parent').all()

    def get_queryset(self):
        base = self.queryset.annotate(
            replies_total=Count('replies', distinct=True),
            reported_by_me=Exists(
                MessageReport.objects.filter(message=OuterRef('pk'), reporter_id=self.request.user.pk)
            ),
        )
        channel_id = int_param(self.request.query_params, 'channel')
        if not channel_id:
            if getattr(self, 'detail', False):
                return base.filter(channel__in=discoverable_channels_for(self.request.user))
            return base.none()
        accessible_channels = discoverable_channels_for(self.request.user).filter(id=channel_id)
        if not accessible_channels.exists():
            return base.none()
        queryset = base.filter(channel_id=channel_id).order_by(*MESSAGE_TIMELINE)
        parent = int_param(self.request.query_params, 'parent')
        if parent:
            queryset = queryset.filter(parent_id=parent)
        before = int_param(self.request.query_params, 'before')
        if before:
            anchor = ChannelMessage.objects.filter(pk=before, channel_id=channel_id).values_list('created_at', 'id').first()
            if anchor is None:
                raise drf_serializers.ValidationError({'before': ['Select a message in this conversation.']})
            queryset = queryset.filter(keyset_filter(MESSAGE_TIMELINE, anchor))
        return queryset

    # Polling: a list response carries a weak ETag over what the page shows
    # (ids, edit times, parent edit times, reply counts, the caller's reports).
    # A poll sending it back in If-None-Match gets 304 from one narrow query
    # instead of the page query, the count query and 50 serialised messages.
    ETAG_FIELDS = ('id', 'updated_at', 'parent__updated_at', 'reported_by_me', 'replies_total')

    def _page_bounds(self):
        page = self.request.query_params.get('page', '1')
        size = self.paginator.get_page_size(self.request)
        if not page.isdigit() or int(page) < 1 or not size:
            return None
        start = (int(page) - 1) * size
        return start, start + size

    def _etag(self, rows, bounds):
        before = self.request.query_params.get('before', '')
        digest = hashlib.sha256(f'{self.request.user.pk}:{get_language()}:{bounds}:{before}'.encode())
        for row in rows:
            digest.update(repr(tuple(row)).encode())
        return f'W/"{digest.hexdigest()[:32]}"'

    def list(self, request, *args, **kwargs):
        # get_queryset() does the channel access check, so the ETag is scoped exactly like the list.
        queryset = self.filter_queryset(self.get_queryset())
        bounds = self._page_bounds()
        sent = request.headers.get('If-None-Match')
        if sent and bounds is not None:
            rows = queryset.values_list(*self.ETAG_FIELDS)[bounds[0]:bounds[1]]
            etag = self._etag(rows, bounds)
            if etag.removeprefix('W/') in {tag.strip().removeprefix('W/') for tag in sent.split(',')}:
                return Response(status=status.HTTP_304_NOT_MODIFIED, headers={'ETag': etag})
        page = self.paginate_queryset(queryset)
        if page is None:
            return Response(self.get_serializer(queryset, many=True).data)
        response = self.get_paginated_response(self.get_serializer(page, many=True).data)
        if bounds is not None:
            rows = [
                (item.id, item.updated_at, item.parent.updated_at if item.parent_id else None,
                 item.reported_by_me, item.replies_total)
                for item in page
            ]
            response['ETag'] = self._etag(rows, bounds)
        return response

    def perform_create(self, serializer):
        message = serializer.save(sender=self.request.user)
        MessageChannel.objects.filter(id=message.channel_id).update(
            last_message_at=message.created_at,
            updated_at=timezone.now(),
        )
        # Writing in a conversation means having read it up to here.
        ChannelMembership.objects.filter(channel_id=message.channel_id, user=self.request.user).update(
            last_read_at=message.created_at,
        )

    def perform_update(self, serializer):
        serializer.save(is_edited=True)

    def perform_destroy(self, instance):
        instance.body = ''
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['body', 'deleted_at', 'updated_at'])

    @action(detail=True, methods=['post'])
    def report(self, request, pk=None):
        message = self.get_object()
        if message.deleted_at:
            return Response({'detail': 'Deleted messages cannot be reported.'}, status=400)
        if message.sender_id == request.user.id:
            return Response({'detail': 'You cannot report your own message.'}, status=400)
        if not message.channel.memberships.filter(user=request.user).exists():
            return Response({'detail': 'Join the channel before reporting a message.'}, status=403)
        reason = request.data.get('reason')
        valid_reasons = {choice for choice, _ in MessageReport.Reason.choices}
        if reason not in valid_reasons:
            return Response({'reason': ['Select a valid report reason.']}, status=400)
        details = str(request.data.get('details', '')).strip()
        if len(details) > 2000:
            return Response({'details': ['Report details cannot exceed 2,000 characters.']}, status=400)
        report, created = MessageReport.objects.get_or_create(
            message=message,
            reporter=request.user,
            defaults={'reason': reason, 'details': details},
        )
        if not created:
            return Response({'detail': 'You have already reported this message.'}, status=400)
        return Response({
            'id': report.id,
            'message': message.id,
            'reason': report.reason,
            'status': report.status,
            'created_at': report.created_at,
        }, status=201)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        message = self.get_object()
        if message.channel.kind != MessageChannel.Kind.DISCUSSION:
            return Response({'detail': 'Accepted answers are only available in Discussions.'}, status=400)
        if not message.parent_id:
            return Response({'detail': 'Only a reply can be accepted as an answer.'}, status=400)
        role = channel_membership_role(message.channel, request.user)
        if not can_accept_answer(message.channel, request.user, role):
            return Response({'detail': 'Only the discussion owner or moderator can accept an answer.'}, status=403)
        with transaction.atomic():
            message.channel.messages.filter(is_accepted_answer=True).update(is_accepted_answer=False)
            message.is_accepted_answer = True
            message.save(update_fields=['is_accepted_answer', 'updated_at'])
        return Response(ChannelMessageSerializer(message, context={'request': request}).data)


class MessageReportPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_product_admin:
            return True
        if request.user.role not in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return False
        return MessageChannel.objects.filter(
            memberships__user=request.user,
            memberships__role__in=[ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR],
        ).exists()


class MessageReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageReportSerializer
    permission_classes = [MessageReportPermission]
    # Profiles ride along so identity masking resolves each person's school
    # without a query per report.
    queryset = MessageReport.objects.select_related(
        'message__channel', 'message__sender__student_profile', 'reporter__student_profile', 'reviewed_by',
    ).all()

    def get_queryset(self):
        queryset = self.queryset.filter(
            message__channel__in=moderatable_channels_for(self.request.user),
        )
        status_value = self.request.query_params.get('status')
        if status_value:
            valid_statuses = {choice for choice, _ in MessageReport.Status.choices}
            if status_value not in valid_statuses:
                return queryset.none()
            queryset = queryset.filter(status=status_value)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(message__body__icontains=search)
                | Q(message__channel__name__icontains=search)
                | Q(details__icontains=search)
            )
        return queryset

    def _ensure_independent_review(self, request, report):
        if report.message.sender_id == request.user.id:
            return Response({'detail': 'Another moderator must review a report about your message.'}, status=403)
        return None

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        report = self.get_object()
        blocked = self._ensure_independent_review(request, report)
        if blocked:
            return blocked
        if report.status != MessageReport.Status.PENDING:
            return Response({'detail': 'Only pending reports can be moved to review.'}, status=400)
        report.status = MessageReport.Status.REVIEWING
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        report = self.get_object()
        blocked = self._ensure_independent_review(request, report)
        if blocked:
            return blocked
        if report.status in {MessageReport.Status.RESOLVED, MessageReport.Status.DISMISSED}:
            return Response({'detail': 'This report has already been closed.'}, status=400)
        report.status = MessageReport.Status.DISMISSED
        report.action = MessageReport.Action.NONE
        report.moderator_note = str(request.data.get('moderator_note', '')).strip()[:2000]
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=[
            'status', 'action', 'moderator_note', 'reviewed_by', 'reviewed_at', 'updated_at',
        ])
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        scoped_report = self.get_object()
        blocked = self._ensure_independent_review(request, scoped_report)
        if blocked:
            return blocked
        selected_action = request.data.get('action', MessageReport.Action.NONE)
        valid_actions = {choice for choice, _ in MessageReport.Action.choices}
        if selected_action not in valid_actions:
            return Response({'action': ['Select a valid moderation action.']}, status=400)
        if scoped_report.status in {MessageReport.Status.RESOLVED, MessageReport.Status.DISMISSED}:
            return Response({'detail': 'This report has already been closed.'}, status=400)
        moderator_note = str(request.data.get('moderator_note', '')).strip()[:2000]
        now = timezone.now()
        with transaction.atomic():
            # of=('self',): PostgreSQL cannot lock the nullable side of the outer
            # joins (message__sender, reviewed_by) and only the report needs a lock.
            report = MessageReport.objects.select_for_update(of=('self',)).select_related(
                'message__channel', 'message__sender', 'reporter', 'reviewed_by',
            ).get(pk=scoped_report.pk)
            message = report.message
            if selected_action == MessageReport.Action.CONTENT_REMOVED and not message.deleted_at:
                message.body = ''
                message.deleted_at = now
                message.save(update_fields=['body', 'deleted_at', 'updated_at'])
            elif selected_action in {MessageReport.Action.MUTED_24H, MessageReport.Action.MUTED_7D}:
                membership = ChannelMembership.objects.select_for_update().filter(
                    channel=message.channel,
                    user_id=message.sender_id,
                ).first()
                if not membership:
                    return Response({'detail': 'The message author is no longer a channel member.'}, status=400)
                duration = timedelta(hours=24) if selected_action == MessageReport.Action.MUTED_24H else timedelta(days=7)
                mute_until = now + duration
                if not membership.muted_until or membership.muted_until < mute_until:
                    membership.muted_until = mute_until
                    membership.save(update_fields=['muted_until'])
            MessageReport.objects.filter(
                message=message,
                status__in=[MessageReport.Status.PENDING, MessageReport.Status.REVIEWING],
            ).update(
                status=MessageReport.Status.RESOLVED,
                action=selected_action,
                moderator_note=moderator_note,
                reviewed_by=request.user,
                reviewed_at=now,
                updated_at=now,
            )
        report.refresh_from_db()
        return Response(self.get_serializer(report).data)
