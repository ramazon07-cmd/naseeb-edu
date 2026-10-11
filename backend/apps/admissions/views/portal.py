"""Admissions API views — portal."""
import math
from datetime import date, timedelta
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from apps.users.models import User
from apps.users.serializers import ContactSerializer
from ..models import (
    Booking,
    MeetingAvailability,
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
from ..serializers.portal import CHOOSE_AVAILABLE_TIME, MeetingAvailabilityRepeatSerializer, MeetingAvailabilitySerializer
from ..listing import ListQueryMixin
from ..meetings import clashes, free_slots, overlapping, upcoming_slots, weekly_starts, with_availability
from ..params import int_param
from ..scoping import booking_participants_for, scope_students, visible_students
from .common import CONTACT_LIST_LIMIT, SCREEN_TIME_TEAM_LIMIT


def notice_time(value):
    # Readers may sit in another zone; the notice text says which clock it uses.
    return f"{timezone.localtime(value).strftime('%d %b %Y, %H:%M')} (Tashkent time)"


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

    STUDENT_ACTIONS = {'list', 'retrieve', 'create', 'participants', 'availability', 'cancel', 'reschedule'}
    STAFF_ACTIONS = {'list', 'retrieve', 'create', 'availability', 'availability_repeat', 'approve', 'reject', 'complete', 'cancel', 'reschedule'}

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
        return obj.participant_id == user.id and view.action in {'retrieve', 'approve', 'reject', 'complete', 'cancel', 'reschedule'}


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
        user = self.request.user
        if user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            student_id = int_param(self.request.data, 'student')
            profile = visible_students(user).filter(id=student_id).first()
            if not profile:
                raise drf_serializers.ValidationError({'student': 'Select one of your students.'})
            start = serializer.validated_data['starts_at']
            duration = serializer.validated_data.get('duration_minutes', 45)
            with transaction.atomic():
                # Same per-staff lock as availability and student claims.
                User.objects.select_for_update().get(pk=user.pk)
                if overlapping(Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES), start, duration):
                    raise drf_serializers.ValidationError({'starts_at': 'This time overlaps another meeting.'})
                # Staff books with themselves: confirmed immediately (no self-approval
                # step), the student is told and can still reschedule or cancel.
                booking = serializer.save(student=profile, participant=user, status=Booking.Status.APPROVED)
                participant_name = user.get_full_name() or user.username
                meeting_time = notice_time(booking.starts_at)
                self._notify(
                    booking, 'Meeting confirmed',
                    f'{participant_name} booked "{booking.topic}" with you on {meeting_time}.',
                )
            return
        if user.role != User.Role.STUDENT or not hasattr(user, 'student_profile'):
            # Product admins pass the permission check but neither hold a student profile nor take meetings.
            raise PermissionDenied('Only students and school staff can book meetings.')
        slot = serializer.validated_data.get('availability_slot')
        with transaction.atomic():
            if slot:
                # Same per-staff lock as adding a slot, so two claims cannot both pass the checks.
                User.objects.select_for_update().get(pk=slot.participant_id)
                locked = MeetingAvailability.objects.select_for_update().get(pk=slot.pk)
                # Staff may have moved the slot since the serializer compared it with the request.
                requested = (serializer.validated_data['starts_at'], serializer.validated_data.get('duration_minutes', 45))
                if (locked.starts_at, locked.duration_minutes) != requested:
                    raise drf_serializers.ValidationError({'availability_slot': 'This time just changed. Pick it again.'})
                if locked.bookings.filter(status__in=Booking.OPEN_STATUSES).exists():
                    raise drf_serializers.ValidationError({'availability_slot': 'This time has already been requested.'})
                meetings = Booking.objects.filter(participant_id=slot.participant_id, status__in=Booking.OPEN_STATUSES)
                if overlapping(meetings, locked.starts_at, locked.duration_minutes):
                    raise drf_serializers.ValidationError({'availability_slot': 'This time overlaps another meeting.'})
            booking = serializer.save(student=self.request.user.student_profile, status=Booking.Status.PENDING)
            student_name, _, meeting_time = self._names(booking)
            self._notify_participant(
                booking, 'New meeting request', f'{student_name} requested "{booking.topic}" on {meeting_time}.',
            )

    @action(detail=False, methods=['get'])
    def participants(self, request):
        profile = request.user.student_profile
        return Response(ContactSerializer(
            booking_participants_for(profile).select_related('school')[:CONTACT_LIST_LIMIT],
            many=True,
            context={'request': request},
        ).data)

    @action(detail=False, methods=['get', 'post', 'patch', 'delete'])
    def availability(self, request):
        """Student sees free slots; staff manages only their own dated slots."""
        user = request.user
        staff = user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}
        if request.method != 'GET' and not staff:
            return Response({'detail': 'Only staff can manage availability.'}, status=403)
        if request.method == 'POST':
            payload = MeetingAvailabilitySerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            start = payload.validated_data['starts_at']
            duration = payload.validated_data.get('duration_minutes', 45)
            try:
                with transaction.atomic():
                    # One writer per staff member at a time; the unique start is the last guard.
                    User.objects.select_for_update().get(pk=user.pk)
                    if overlapping(MeetingAvailability.objects.filter(participant=user), start, duration):
                        return Response({'starts_at': 'This time overlaps an existing slot.'}, status=400)
                    if overlapping(Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES), start, duration):
                        return Response({'starts_at': 'This time overlaps an existing meeting.'}, status=400)
                    slot = payload.save(participant=user)
            except IntegrityError:
                return Response({'starts_at': 'This time overlaps an existing slot.'}, status=400)
            return Response(MeetingAvailabilitySerializer(slot).data, status=201)
        if request.method == 'PATCH':
            slot = MeetingAvailability.objects.filter(pk=int_param(request.data, 'id'), participant=user).first()
            if not slot:
                return Response({'detail': 'Slot not found.'}, status=404)
            # A past time is history: moving it forward would turn it into a new, bookable time.
            if slot.starts_at <= timezone.now():
                return Response({'detail': 'This time has already passed. Add a new time instead.'}, status=400)
            payload = MeetingAvailabilitySerializer(slot, data=request.data, partial=True)
            payload.is_valid(raise_exception=True)
            start = payload.validated_data.get('starts_at', slot.starts_at)
            duration = payload.validated_data.get('duration_minutes', slot.duration_minutes)
            try:
                with transaction.atomic():
                    User.objects.select_for_update().get(pk=user.pk)
                    # Open or not, a meeting points at this slot; moving it would rewrite that meeting's time.
                    if slot.bookings.exists():
                        return Response({'detail': 'This time has a meeting on record and cannot be moved. Add a new time instead.'}, status=400)
                    if overlapping(MeetingAvailability.objects.filter(participant=user), start, duration, exclude_pk=slot.pk):
                        return Response({'starts_at': 'This time overlaps an existing slot.'}, status=400)
                    if overlapping(Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES), start, duration):
                        return Response({'starts_at': 'This time overlaps an existing meeting.'}, status=400)
                    slot = payload.save()
            except IntegrityError:
                return Response({'starts_at': 'This time overlaps an existing slot.'}, status=400)
            return Response({**MeetingAvailabilitySerializer(slot).data, 'participant': slot.participant_id, 'available': True})
        if request.method == 'DELETE':
            slot_id = int_param(request.data, 'id')
            slot = MeetingAvailability.objects.filter(pk=slot_id, participant=user).first()
            if not slot:
                return Response({'detail': 'Slot not found.'}, status=404)
            if slot.bookings.filter(status__in=Booking.OPEN_STATUSES).exists():
                return Response({'detail': 'Cancel the meeting before removing this slot.'}, status=400)
            slot.delete()
            return Response(status=204)
        # Rescheduling: the caller's own meeting (as student or participant) does not block the times it overlaps.
        # Another id, or one the caller cannot see, is a 404 exactly like a missing one.
        moving = int_param(request.query_params, 'reschedule')
        if moving is not None and not self.get_queryset().filter(pk=moving).exists():
            return Response({'detail': 'Meeting not found.'}, status=404)
        if staff:
            # `editable`: no meeting, of any status, points at the slot (the PATCH rule).
            slots = MeetingAvailability.objects.filter(participant=user).annotate(
                has_history=Exists(Booking.objects.filter(availability_slot=OuterRef('pk'))),
            )
            return Response([
                {**MeetingAvailabilitySerializer(slot).data, 'participant': slot.participant_id, 'available': free,
                 'editable': not slot.has_history}
                for slot, free in with_availability(upcoming_slots(slots), moving=moving)
            ])
        overview = False
        if user.role == User.Role.STUDENT:
            profile = user.student_profile
            participant_id = request.query_params.get('participant')
            participants = booking_participants_for(profile)
            if participant_id is not None:
                participant_id = int_param(request.query_params, 'participant')
                if not participants.filter(pk=participant_id).exists():
                    return Response({'participant': 'Choose a staff member from your school.'}, status=400)
                slots = MeetingAvailability.objects.filter(participant_id=participant_id)
            else:
                allowed_ids = participants.values_list('id', flat=True)[:CONTACT_LIST_LIMIT]
                slots = MeetingAvailability.objects.filter(participant_id__in=allowed_ids)
                overview = True
        else:
            return Response({'detail': 'Availability is unavailable for this role.'}, status=403)
        # Students only ever see times they can still take; taken ones are dropped before any cap.
        return Response([
            {**MeetingAvailabilitySerializer(slot).data, 'participant': slot.participant_id, 'available': True}
            for slot in upcoming_slots(free_slots(slots, moving=moving), overview=overview)
        ])

    @action(detail=False, methods=['post'], url_path='availability/repeat')
    def availability_repeat(self, request):
        """Weekly slots up to 12 weeks ahead; times that are past or overlap are skipped, not errors."""
        user = request.user
        if user.role not in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return Response({'detail': 'Only staff can manage availability.'}, status=403)
        payload = MeetingAvailabilityRepeatSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        duration = data['duration_minutes']
        now = timezone.now()
        starts = list(weekly_starts(set(data['weekdays']), data['time'], data['start_date'], data['end_date'], data['timezone']))
        future = [start for start in starts if start > now]
        created = []
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                if future:
                    # One read of the whole range (slots and open meetings), then checks in memory.
                    first = min(future)
                    span = math.ceil((max(future) - first).total_seconds() / 60) + duration
                    taken = (
                        overlapping(MeetingAvailability.objects.filter(participant=user), first, span)
                        + overlapping(Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES), first, span)
                    )
                    for start in future:
                        if not clashes(taken, start, duration):
                            slot = MeetingAvailability(participant=user, starts_at=start, duration_minutes=duration)
                            created.append(slot)
                            taken.append(slot)
                    created = MeetingAvailability.objects.bulk_create(created)
        except IntegrityError:
            return Response({'starts_at': 'This time overlaps an existing slot.'}, status=400)
        skipped = len(starts) - len(created)
        return Response({
            'created': len(created),
            'skipped': skipped,
            'slots': [{**MeetingAvailabilitySerializer(slot).data, 'participant': user.id, 'available': True} for slot in created],
        }, status=201 if created else 200)

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
        return student, participant, notice_time(booking.starts_at)

    def _notify(self, booking, title, message):
        # Student notifications are also the assigned counselor's feed (see NotificationViewSet).
        Notification.objects.create(
            student=booking.student, title=title, message=message, kind=Notification.Kind.MEETING,
        )

    def _notify_participant(self, booking, title, message):
        # A separate row addressed to the staff member: their bell (and reading it) never touches the student's feed.
        if booking.participant_id:
            Notification.objects.create(
                student=booking.student, recipient_id=booking.participant_id,
                title=title, message=message, kind=Notification.Kind.MEETING, target_id=booking.pk,
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
            # The UI calls an approved meeting "confirmed".
            word = 'confirmed' if target_status == Booking.Status.APPROVED else booking.get_status_display().lower()
            self._notify(
                booking, f'Meeting {word}', f'Your meeting with {participant_name} on {meeting_time} is now {word}.',
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
                self._notify_participant(booking, 'Meeting cancelled', message)
            else:
                message = f'Your meeting with {participant_name} on {meeting_time} was cancelled.'
            self._notify(booking, 'Meeting cancelled', message)
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Propose a new time; the request goes back to the participant for approval."""
        payload = BookingRescheduleSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        starts_at = payload.validated_data['starts_at']
        with transaction.atomic():
            booking = self._locked_booking()
            student_moves = request.user.role == User.Role.STUDENT
            # Staff moves are confirmed at once, so only the people who own the meeting may make them.
            if not student_moves and request.user.pk not in {booking.participant_id, booking.student.assigned_counselor_id}:
                return Response({'detail': 'Only the meeting participant or the student’s counselor can move it.'}, status=403)
            if booking.status not in Booking.OPEN_STATUSES or booking.has_started:
                return Response({'detail': 'Only a meeting that has not started yet can be rescheduled.'}, status=400)
            # The same participant rule as a new request: staff of the student's current school.
            if not booking_participants_for(booking.student).filter(pk=booking.participant_id).exists():
                return Response(
                    {'participant': ['This staff member is no longer available. Request a new meeting instead.']},
                    status=400,
                )
            duration = payload.validated_data.get('duration_minutes', booking.duration_minutes)
            if (booking.starts_at, booking.duration_minutes) == (starts_at, duration):
                # Same time (so also the same slot): nothing moves, whatever the status.
                return Response(self.get_serializer(booking).data)
            slot = payload.validated_data.get('availability_slot')
            # Students move only onto a published slot; staff may pick one of theirs or any free time.
            if request.user.role == User.Role.STUDENT and not slot:
                return Response({'availability_slot': CHOOSE_AVAILABLE_TIME}, status=400)
            # Same per-staff lock as availability changes and new requests.
            User.objects.select_for_update().get(pk=booking.participant_id)
            if slot:
                slot = MeetingAvailability.objects.select_for_update().get(pk=slot.pk)
                if slot.participant_id != booking.participant_id or slot.starts_at != starts_at or slot.duration_minutes != duration:
                    return Response({'availability_slot': 'Choose a time from this staff member’s availability.'}, status=400)
                if slot.bookings.filter(status__in=Booking.OPEN_STATUSES).exclude(pk=booking.pk).exists():
                    return Response({'availability_slot': 'This time has already been requested.'}, status=400)
            meetings = Booking.objects.filter(participant_id=booking.participant_id, status__in=Booking.OPEN_STATUSES)
            if overlapping(meetings, starts_at, duration, exclude_pk=booking.pk):
                return Response({'availability_slot' if slot else 'starts_at': 'This time overlaps another meeting.'}, status=400)
            booking.previous_starts_at = booking.starts_at
            booking.starts_at = starts_at
            booking.duration_minutes = duration
            booking.availability_slot = slot
            # The participant must agree to any time they did not pick themselves.
            moved_by_participant = request.user.pk == booking.participant_id
            booking.status = Booking.Status.APPROVED if moved_by_participant else Booking.Status.PENDING
            booking.save(update_fields=['previous_starts_at', 'starts_at', 'duration_minutes', 'availability_slot', 'status', 'updated_at'])
            student_name, participant_name, meeting_time = self._names(booking)
            if student_moves:
                title = 'Meeting reschedule requested'
                self._notify_participant(booking, title, f'{student_name} asked to move "{booking.topic}" to {meeting_time}.')
                message = f'You asked to move "{booking.topic}" to {meeting_time}. Waiting for {participant_name} to confirm.'
            else:
                title = 'Meeting moved'
                message = f'Your meeting with {participant_name} was moved to {meeting_time}.'
                if not moved_by_participant:
                    mover = request.user.get_full_name() or request.user.username
                    self._notify_participant(booking, 'Meeting moved', f'{mover} moved "{booking.topic}" with {student_name} to {meeting_time}. Please confirm.')
            self._notify(booking, title, message)
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
    def entry_key(entry, today):
        """(date, page, seconds) for a valid entry, else None."""
        if not isinstance(entry, dict):
            return None
        page = str(entry.get('page') or '').strip().lower()
        if not page or len(page) > 80 or not all(character.isalnum() or character in {'_', '-'} for character in page):
            return None
        try:
            seconds = int(entry.get('seconds'))
            tracked_date = date.fromisoformat(str(entry.get('date') or today.isoformat()))
        except (TypeError, ValueError):
            return None
        if not 1 <= seconds <= 300:
            return None
        # The browser dates entries on its own clock, which can already be tomorrow here.
        if tracked_date > today + timedelta(days=1) or tracked_date < today - timedelta(days=7):
            return None
        return tracked_date, page, seconds

    @classmethod
    def parse_entries(cls, raw_entries):
        """Seconds per (date, page) and the number of entries skipped as invalid.

        The client drops a batch once it is accepted, so one bad entry is skipped
        rather than failing (and endlessly retrying) the rest.
        """
        if not isinstance(raw_entries, list) or not raw_entries or len(raw_entries) > 50:
            raise drf_serializers.ValidationError({'entries': 'Send between 1 and 50 screen-time entries.'})
        today = timezone.localdate()
        aggregated = {}
        skipped = 0
        for entry in raw_entries:
            parsed = cls.entry_key(entry, today)
            if parsed is None:
                skipped += 1
                continue
            tracked_date, page, seconds = parsed
            aggregated[(tracked_date, page)] = aggregated.get((tracked_date, page), 0) + seconds
        if any(seconds > 600 for seconds in aggregated.values()):
            raise drf_serializers.ValidationError({'seconds': 'A single batch cannot exceed 10 minutes per page.'})
        return aggregated, skipped

    @action(detail=False, methods=['post'])
    def track(self, request):
        entries, skipped = self.parse_entries(request.data.get('entries'))
        extra = {'skipped': skipped} if skipped else {}
        if not entries:
            return Response({'tracked_seconds': 0, 'entries': 0, **extra})
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
        return Response({'tracked_seconds': sum(entries.values()), 'entries': len(entries), **extra})

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
