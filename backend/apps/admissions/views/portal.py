"""Admissions API views — portal."""
from datetime import date, timedelta
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from apps.users.models import User
from apps.users.serializers import ContactSerializer
from ..models import (
    Booking,
    Notification,
    ProgramService,
    ScreenTimeDaily,
    StudentProfile,
    StudentMessage,
)
from ..serializers import (
    BookingRescheduleSerializer,
    BookingSerializer,
    ProgramServiceSerializer,
    ScreenTimeDailySerializer,
    StudentMessageSerializer,
)
from ..listing import ListQueryMixin
from ..params import int_param
from ..scoping import booking_participants_for, scope_students, visible_students
from .common import CONTACT_LIST_LIMIT, SCREEN_TIME_TEAM_LIMIT


class StudentPortalPermission(permissions.BasePermission):
    """Keep the Crimson-inspired portal modules isolated to signed-in students."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.STUDENT
            and hasattr(request.user, 'student_profile')
        )

    def has_object_permission(self, request, view, obj):
        profile = request.user.student_profile
        owner = getattr(obj, 'student', None)
        if owner is not None:
            return getattr(owner, 'id', None) == profile.id
        return request.method in permissions.SAFE_METHODS


class StudentCollaborationPermission(permissions.BasePermission):
    """Allow students and their assigned counselors to share legacy direct messages."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_organization:
            return False
        if request.user.is_counselor_like:
            return not (view.basename == 'bookings' and view.action == 'create')
        return bool(
            request.user.role == User.Role.STUDENT
            and hasattr(request.user, 'student_profile')
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            return True
        if user.role == User.Role.COUNSELOR:
            if isinstance(obj, Booking):
                return obj.counselor_id == user.id
            if isinstance(obj, StudentMessage):
                return user.id in {obj.sender_id, obj.recipient_id}
            return False
        return getattr(obj, 'student_id', None) == user.student_profile.id


class BookingPermission(permissions.BasePermission):
    """Keep meeting requests scoped to the student and the selected staff participant."""

    STUDENT_ACTIONS = {'list', 'retrieve', 'create', 'participants', 'cancel', 'reschedule'}
    STAFF_ACTIONS = {'list', 'retrieve', 'approve', 'reject', 'complete', 'cancel'}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return view.action in self.STUDENT_ACTIONS
        if user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return view.action in self.STAFF_ACTIONS
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return obj.student_id == user.student_profile.id and view.action in {'retrieve', 'cancel', 'reschedule'}
        return obj.participant_id == user.id and view.action in {'retrieve', 'approve', 'reject', 'complete', 'cancel'}


class StudentPortalOwnedViewSet(viewsets.ModelViewSet):
    permission_classes = [StudentPortalPermission]

    def get_queryset(self):
        return self.queryset.filter(student=self.request.user.student_profile)


class BookingViewSet(ListQueryMixin, viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [BookingPermission]
    queryset = Booking.objects.select_related('student__user', 'participant', 'participant__school').all()
    search_fields = ('topic',)
    search_student_path = 'student'
    int_filters = {'student': 'student_id', 'participant': 'participant_id'}
    choice_filters = {'status': ('status', Booking.Status.choices)}
    date_filters = {'starts': 'starts_at'}
    ordering_options = {
        'starts': ('starts_at', 'id'), '-starts': ('-starts_at', '-id'), '-created': ('-created_at', '-id'),
    }
    default_cursor_ordering = 'starts'

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return self.queryset
        if user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            # Meetings stay with the school: staff who moved on lose them.
            if not user.school_id:
                return self.queryset.none()
            return self.queryset.filter(participant=user, student__school_id=user.school_id)
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return self.queryset.filter(student=user.student_profile)
        return self.queryset.none()

    def perform_create(self, serializer):
        profile = self.request.user.student_profile
        serializer.save(student=profile, status=Booking.Status.PENDING)

    @action(detail=False, methods=['get'])
    def participants(self, request):
        profile = request.user.student_profile
        return Response(ContactSerializer(
            booking_participants_for(profile).select_related('school')[:CONTACT_LIST_LIMIT],
            many=True,
            context={'request': request},
        ).data)

    def _locked_booking(self):
        """The booking this request may act on (404 otherwise), row-locked until commit."""
        booking = self.get_object()
        return (
            Booking.objects.select_for_update(of=('self',))
            .select_related('student__user', 'participant__school').get(pk=booking.pk)
        )

    @staticmethod
    def _names(booking):
        student = booking.student.user.get_full_name() or booking.student.user.username
        participant = (
            booking.participant.get_full_name() or booking.participant.username
            if booking.participant else 'your meeting participant'
        )
        return student, participant, timezone.localtime(booking.starts_at).strftime('%d %b %Y, %H:%M')

    def _notify(self, booking, title, message):
        # Student notifications are also the assigned counselor's feed (see NotificationViewSet).
        Notification.objects.create(
            student=booking.student, title=title, message=message, kind=Notification.Kind.MEETING,
        )

    def _transition(self, target_status, allowed_from):
        with transaction.atomic():
            booking = self._locked_booking()
            if booking.status == target_status:
                return Response(self.get_serializer(booking).data)
            if booking.status not in allowed_from:
                return Response(
                    {'detail': f'A {booking.get_status_display().lower()} meeting cannot be changed to {target_status}.'},
                    status=400,
                )
            if target_status == Booking.Status.APPROVED and booking.is_expired:
                return Response({'detail': 'This request expired before it was confirmed.'}, status=400)
            booking.status = target_status
            booking.save(update_fields=['status', 'updated_at'])
            _, participant_name, meeting_time = self._names(booking)
            self._notify(
                booking,
                f'Meeting {booking.get_status_display().lower()}',
                f'Your meeting with {participant_name} on {meeting_time} is now {booking.get_status_display().lower()}.',
            )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._transition(Booking.Status.APPROVED, {Booking.Status.PENDING})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._transition(Booking.Status.REJECTED, {Booking.Status.PENDING})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        return self._transition(Booking.Status.COMPLETED, {Booking.Status.APPROVED})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """The student or the staff participant calls off a meeting that has not started."""
        with transaction.atomic():
            booking = self._locked_booking()
            if booking.status == Booking.Status.CANCELLED:
                return Response(self.get_serializer(booking).data)
            if booking.status not in Booking.OPEN_STATUSES or booking.has_started:
                return Response({'detail': 'Only a meeting that has not started yet can be cancelled.'}, status=400)
            booking.status = Booking.Status.CANCELLED
            booking.save(update_fields=['status', 'updated_at'])
            student_name, participant_name, meeting_time = self._names(booking)
            if request.user.role == User.Role.STUDENT:
                message = f'{student_name} cancelled the meeting "{booking.topic}" on {meeting_time}.'
            else:
                message = f'Your meeting with {participant_name} on {meeting_time} was cancelled.'
            self._notify(booking, 'Meeting cancelled', message)
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Propose a new time; the request goes back to the participant for approval."""
        payload = BookingRescheduleSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        starts_at = payload.validated_data['starts_at']
        with transaction.atomic():
            booking = self._locked_booking()
            if booking.status not in Booking.OPEN_STATUSES or booking.has_started:
                return Response({'detail': 'Only a meeting that has not started yet can be rescheduled.'}, status=400)
            # The same participant rule as a new request: staff of the student's current school.
            if not booking_participants_for(booking.student).filter(pk=booking.participant_id).exists():
                return Response(
                    {'participant': ['This staff member is no longer available. Request a new meeting instead.']},
                    status=400,
                )
            duration = payload.validated_data.get('duration_minutes', booking.duration_minutes)
            if (booking.status, booking.starts_at, booking.duration_minutes) == (Booking.Status.PENDING, starts_at, duration):
                return Response(self.get_serializer(booking).data)
            booking.starts_at = starts_at
            booking.duration_minutes = duration
            booking.status = Booking.Status.PENDING
            booking.save(update_fields=['starts_at', 'duration_minutes', 'status', 'updated_at'])
            student_name, _, meeting_time = self._names(booking)
            self._notify(
                booking, 'Meeting reschedule requested',
                f'{student_name} asked to move "{booking.topic}" to {meeting_time}.',
            )
        return Response(self.get_serializer(booking).data)


class StudentMessageViewSet(viewsets.ModelViewSet):
    serializer_class = StudentMessageSerializer
    permission_classes = [StudentCollaborationPermission]
    queryset = StudentMessage.objects.select_related('student__user', 'sender', 'recipient').all()
    # ?cursor= pages newest first; a thread is read from its latest message.
    keyset_ordering = ('-created_at', '-id')

    def get_queryset(self):
        user = self.request.user
        if user.is_product_admin:
            return self.queryset
        if user.role == User.Role.COUNSELOR:
            # Only threads with students the counselor still serves in their
            # current school; a move or reassignment ends access to the rest.
            return scope_students(
                self.queryset.filter(Q(sender=user) | Q(recipient=user)), user, via='student',
            )
        return self.queryset.filter(student=user.student_profile)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == User.Role.COUNSELOR or user.is_counselor_like:
            student_id = int_param(self.request.data, 'student')
            profile = visible_students(user).filter(id=student_id, assigned_counselor=user).first()
            if not profile:
                raise drf_serializers.ValidationError({'student': 'Select one of your assigned students.'})
            serializer.save(student=profile, sender=user, recipient=profile.user)
            return
        profile = user.student_profile
        if not profile.assigned_counselor:
            raise drf_serializers.ValidationError({'recipient': 'A counselor has not been assigned yet.'})
        serializer.save(student=profile, sender=user, recipient=profile.assigned_counselor)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        message = self.get_object()
        if message.recipient_id == request.user.id and not message.is_read:
            message.is_read = True
            message.save(update_fields=['is_read', 'updated_at'])
        return Response(StudentMessageSerializer(message, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        # Student portal only: messages addressed to the caller in their own
        # thread. Staff inboxes are left as they were.
        updated = self.get_queryset().filter(recipient=request.user, student__user=request.user, is_read=False).update(
            is_read=True, updated_at=timezone.now(),
        )
        return Response({'updated': updated})


class ProgramServicePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return user.role in {
                User.Role.ADMIN, User.Role.COUNSELOR, User.Role.ORGANIZATION, User.Role.STUDENT,
            } or user.is_superuser
        return user.is_superuser or user.role in {User.Role.ADMIN, User.Role.COUNSELOR}

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            return bool(
                user.school_id
                and obj.student.school_id == user.school_id
                and obj.student.assigned_counselor_id == user.id
            )
        if user.role == User.Role.ORGANIZATION:
            return request.method in permissions.SAFE_METHODS and obj.student.school_id == user.school_id
        return request.method in permissions.SAFE_METHODS and obj.student.user_id == user.id


class ProgramServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramServiceSerializer
    permission_classes = [ProgramServicePermission]
    queryset = ProgramService.objects.select_related('student__user', 'student__school', 'mentor').all()

    def get_queryset(self):
        if self.request.user.role == User.Role.TEACHER:
            return self.queryset.none()
        return scope_students(self.queryset, self.request.user, via='student')


class ScreenTimeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScreenTimeDailySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ScreenTimeDaily.objects.select_related('user').all()
    http_method_names = ['get', 'post', 'head', 'options']

    def student_profiles_for_scope(self):
        user = self.request.user
        if user.role == User.Role.STUDENT:
            return StudentProfile.objects.none()
        return visible_students(user, StudentProfile.objects.select_related('user', 'school'))

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            student_user_ids = self.student_profiles_for_scope().values_list('user_id', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=student_user_ids))
        if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
            student_user_ids = self.student_profiles_for_scope().values_list('user_id', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=student_user_ids))
        return queryset.filter(user=user)

    @staticmethod
    def parse_entries(raw_entries):
        if not isinstance(raw_entries, list) or not raw_entries or len(raw_entries) > 50:
            raise drf_serializers.ValidationError({'entries': 'Send between 1 and 50 screen-time entries.'})
        today = timezone.localdate()
        oldest_allowed = today - timedelta(days=7)
        aggregated = {}
        for entry in raw_entries:
            if not isinstance(entry, dict):
                raise drf_serializers.ValidationError({'entries': 'Every entry must be an object.'})
            page = str(entry.get('page') or '').strip().lower()
            if not page or len(page) > 80 or not all(character.isalnum() or character in {'_', '-'} for character in page):
                raise drf_serializers.ValidationError({'page': 'Use a valid application page key.'})
            try:
                seconds = int(entry.get('seconds'))
            except (TypeError, ValueError):
                raise drf_serializers.ValidationError({'seconds': 'Active seconds must be an integer.'})
            if seconds < 1 or seconds > 300:
                raise drf_serializers.ValidationError({'seconds': 'Each entry must contain 1–300 active seconds.'})
            try:
                tracked_date = date.fromisoformat(str(entry.get('date') or today.isoformat()))
            except ValueError:
                raise drf_serializers.ValidationError({'date': 'Use YYYY-MM-DD.'})
            if tracked_date > today or tracked_date < oldest_allowed:
                raise drf_serializers.ValidationError({'date': 'Offline screen time can only be submitted within 7 days.'})
            key = (tracked_date, page)
            aggregated[key] = aggregated.get(key, 0) + seconds
        if any(seconds > 600 for seconds in aggregated.values()):
            raise drf_serializers.ValidationError({'seconds': 'A single batch cannot exceed 10 minutes per page.'})
        return aggregated

    @action(detail=False, methods=['post'])
    def track(self, request):
        entries = self.parse_entries(request.data.get('entries'))
        # One upsert for the whole batch: every open tab sends this every 30 s.
        table = connection.ops.quote_name(ScreenTimeDaily._meta.db_table)
        now = timezone.now()
        rows = [(request.user.pk, tracked_date, page, seconds, now) for (tracked_date, page), seconds in entries.items()]
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table} (user_id, date, page, active_seconds, sessions, last_seen_at) VALUES '
                + ', '.join(['(%s, %s, %s, %s, 1, %s)'] * len(rows))
                + ' ON CONFLICT (user_id, date, page) DO UPDATE SET'
                f' active_seconds = {table}.active_seconds + EXCLUDED.active_seconds,'
                f' sessions = {table}.sessions + 1, last_seen_at = EXCLUDED.last_seen_at',
                [value for row in rows for value in row],
            )
        return Response({'tracked_seconds': sum(entries.values()), 'entries': len(entries)})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        try:
            days = min(31, max(1, int(request.query_params.get('days', 7))))
        except (TypeError, ValueError):
            days = 7
        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)
        own = ScreenTimeDaily.objects.filter(user=request.user, date__gte=start_date)
        daily_rows = list(
            own.values('date').annotate(seconds=Sum('active_seconds')).order_by('date')
        )
        page_rows = list(
            own.values('page').annotate(seconds=Sum('active_seconds')).order_by('-seconds', 'page')
        )
        scope = self.student_profiles_for_scope()
        scope_user_ids = scope.order_by().values('user_id')
        team_total = scope.count()
        period_totals = {
            row['user_id']: row['seconds'] or 0
            for row in ScreenTimeDaily.objects.filter(
                user_id__in=scope_user_ids, date__gte=start_date
            ).values('user_id').annotate(seconds=Sum('active_seconds'))
        }
        today_totals = {
            row['user_id']: row['seconds'] or 0
            for row in ScreenTimeDaily.objects.filter(
                user_id__in=scope_user_ids, date=today
            ).values('user_id').annotate(seconds=Sum('active_seconds'))
        }
        # Never serialize an unbounded roster (an admin scope is every
        # student). Most active first, then fill with idle students by name.
        limit = SCREEN_TIME_TEAM_LIMIT
        active_ids = sorted(
            period_totals, key=lambda user_id: (-today_totals.get(user_id, 0), -period_totals[user_id]),
        )[:limit]
        profiles = list(scope.filter(user_id__in=active_ids))
        if len(profiles) < limit:
            profiles += list(
                scope.exclude(user_id__in=active_ids)
                .order_by('user__first_name', 'user__last_name', 'id')[:limit - len(profiles)]
            )
        team = [
            {
                'student': profile.id,
                'user': profile.user_id,
                'name': profile.user.get_full_name() or profile.user.username,
                'school': profile.school.name if profile.school else profile.school_name,
                'today_seconds': today_totals.get(profile.user_id, 0),
                'period_seconds': period_totals.get(profile.user_id, 0),
            }
            for profile in profiles
        ]
        team.sort(key=lambda item: (-item['today_seconds'], item['name']))
        return Response({
            'timezone': settings.TIME_ZONE,
            'retention_days': getattr(settings, 'SCREEN_TIME_RETENTION_DAYS', 365),
            'period_days': days,
            'today': today,
            'own': {
                'today_seconds': own.filter(date=today).aggregate(total=Sum('active_seconds'))['total'] or 0,
                'period_seconds': own.aggregate(total=Sum('active_seconds'))['total'] or 0,
                'daily': daily_rows,
                'pages': page_rows,
            },
            'team': team,
            'team_total': team_total,
            'team_truncated': team_total > len(team),
            'privacy': 'Only aggregate active seconds by user, day, and application page are stored.',
        })


class StudentTeamView(APIView):
    permission_classes = [StudentPortalPermission]

    def get(self, request):
        profile = request.user.student_profile
        team = []
        # Only people the student can actually reach (see messaging_contacts_for).
        counselor = profile.assigned_counselor
        if counselor and counselor.is_active and counselor.school_id == profile.school_id:
            team.append({
                'id': counselor.id,
                'name': counselor.get_full_name() or counselor.username,
                'role': counselor.position or 'Education counselor',
                'email': counselor.email,
                'phone': counselor.phone,
                'kind': 'counselor',
            })
        if profile.school:
            organization_users = profile.school.users.filter(
                role=User.Role.ORGANIZATION, is_active=True,
            ).order_by('first_name', 'id')
            for member in organization_users:
                team.append({
                    'id': member.id,
                    'name': member.get_full_name() or member.username,
                    'role': member.position or f'{profile.school.name} coordinator',
                    'email': member.email,
                    'phone': member.phone,
                    'kind': 'school',
                })
        return Response(team)
