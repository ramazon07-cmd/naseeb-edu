"""Admissions API views — parents."""
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils.text import slugify
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.users.credentials import issue_temporary_credential
from apps.users.entitlements import feature_not_in_plan, links_with_feature, school_has_feature
from apps.users.models import User
from apps.users.services import audit_product_action
from ..models import Application, Booking, ParentStudentLink, Task
from ..params import int_param
from ..serializers import ParentInviteSerializer, ParentLinkSectionsSerializer, ParentStudentLinkSerializer
from ..scoping import parent_visible_links, scope_students
from ..progress import OPEN_TASK_STATUSES, attach_progress_stats


INACTIVE_CHILD_MESSAGE = 'This student account is not active, so the invitation cannot be accepted.'
REVOKED_LINK_MESSAGE = 'This parent access was disconnected; send a new invitation instead.'


class ParentLinkPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            return view.action in {'list', 'retrieve', 'invite', 'revoke', 'sections'}
        if user.role == User.Role.PARENT:
            return view.action in {'list', 'retrieve', 'accept', 'revoke'}
        return False

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
        return user.role == User.Role.PARENT and obj.parent_id == user.id


class ParentStudentLinkViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ParentStudentLinkSerializer
    permission_classes = [ParentLinkPermission]
    queryset = ParentStudentLink.objects.select_related(
        'parent', 'student__user', 'student__school', 'student__assigned_counselor', 'invited_by'
    ).all()
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            queryset = self.queryset
        elif user.role == User.Role.COUNSELOR:
            queryset = scope_students(self.queryset, user, via='student')
        elif user.role == User.Role.PARENT:
            return self.queryset.filter(parent=user)
        else:
            return self.queryset.none()
        # Staff open one student's family access (the invite dialog).
        student = int_param(self.request.query_params, 'student')
        return queryset.filter(student_id=student) if student else queryset

    @staticmethod
    def unique_parent_username(email):
        base = slugify(email.split('@')[0])[:130] or 'parent'
        username = base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{base[:145 - len(str(suffix))]}-{suffix}'
        return username

    @action(detail=False, methods=['post'])
    def invite(self, request):
        if not (
            request.user.is_superuser
            or request.user.role in {User.Role.ADMIN, User.Role.COUNSELOR}
        ):
            return Response({'detail': 'Only an admin or assigned counselor can invite a parent.'}, status=403)
        serializer = ParentInviteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        student = values['student']
        if not school_has_feature(student.school_id, 'parent_portal'):
            raise feature_not_in_plan(request)

        email = values['email'].lower()
        with transaction.atomic():
            parent, created_account = self.parent_for_invite(email, values, request)
            if parent is not None:
                link, created_link = ParentStudentLink.objects.select_for_update().get_or_create(
                    parent=parent,
                    student=student,
                    defaults={
                        'relationship': values['relationship'],
                        'can_view_applications': values['can_view_applications'],
                        'can_view_documents': values['can_view_documents'],
                        'can_view_meetings': values['can_view_meetings'],
                        'invited_by': request.user,
                    },
                )
                refreshed = not created_link and link.status != ParentStudentLink.Status.ACTIVE
                # Re-sending a pending invitation only refreshes it; a new or
                # revived invitation is what the audit trail records.
                revived = refreshed and link.status != ParentStudentLink.Status.PENDING
                if refreshed:
                    link.relationship = values['relationship']
                    link.status = ParentStudentLink.Status.PENDING
                    link.can_view_applications = values['can_view_applications']
                    link.can_view_documents = values['can_view_documents']
                    link.can_view_meetings = values['can_view_meetings']
                    link.invited_by = request.user
                    link.consented_at = None
                    link.revoked_at = None
                    link.save()
                if created_link or revived:
                    audit_product_action(
                        actor=request.user,
                        action='parent.invited',
                        target=parent,
                        school=student.school_id,
                        metadata={'student': student.pk, 'link': link.pk, 'created_account': created_account},
                    )
        # One response for every outcome (new parent, existing parent, active
        # link, address owned by a non-parent account), so an invitation never
        # reveals whether an address is registered or whose it is.
        return Response({
            'detail': self.INVITE_RECORDED,
            'email': email,
        }, status=201)

    INVITE_RECORDED = (
        'Invitation recorded. The parent signs in with this email address and accepts it; '
        'an existing parent account keeps its own password.'
    )

    def parent_for_invite(self, email, values, request):
        """(parent account for ``email``, created now?); the account is ``None`` when unusable."""
        parent = None
        for _ in range(3):
            existing = User.objects.filter(email__iexact=email).first()
            if existing is not None:
                return (existing if existing.role == User.Role.PARENT else None), False
            try:
                with transaction.atomic():
                    parent = User.objects.create_user(
                        username=self.unique_parent_username(email),
                        email=email,
                        password=None,
                        first_name=values.get('first_name', ''),
                        last_name=values.get('last_name', ''),
                        role=User.Role.PARENT,
                    )
                break
            except IntegrityError:
                continue  # a concurrent request took the address or username
        if parent is None:
            return None, False
        # Same lifecycle as every staff-issued password: single use,
        # must be changed at first sign-in, audited.
        parent, _, _, _ = issue_temporary_credential(
            user=parent, issued_by=request.user, raw_password=values['password'], request=request,
        )
        return parent, True

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        link = self.get_object()
        if request.user.role != User.Role.PARENT or link.parent_id != request.user.id:
            return Response({'detail': 'Only the invited parent can accept this link.'}, status=403)
        if link.status != ParentStudentLink.Status.PENDING:
            return Response({'detail': 'Only a pending invitation can be accepted.'}, status=409)
        if not parent_visible_links(ParentStudentLink.objects.filter(pk=link.pk)).exists():
            return Response({'detail': INACTIVE_CHILD_MESSAGE, 'code': 'student_inactive'}, status=409)
        if not links_with_feature(ParentStudentLink.objects.filter(pk=link.pk), 'parent_portal').exists():
            raise feature_not_in_plan(request)
        link.status = ParentStudentLink.Status.ACTIVE
        link.consented_at = timezone.now()
        link.revoked_at = None
        link.save(update_fields=['status', 'consented_at', 'revoked_at', 'updated_at'])
        return Response(self.get_serializer(link).data)

    @action(detail=True, methods=['post'])
    def sections(self, request, pk=None):
        """Change what an active or pending link shares, without disconnecting the family."""
        link = self.get_object()
        if link.status == ParentStudentLink.Status.REVOKED:
            return Response({'detail': REVOKED_LINK_MESSAGE, 'code': 'link_revoked'}, status=409)
        serializer = ParentLinkSectionsSerializer(link, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = {
            field: value for field, value in serializer.validated_data.items() if getattr(link, field) != value
        }
        if changes:
            serializer.save()
            audit_product_action(
                actor=request.user, action='parent.permissions_changed', target=link.parent,
                school=link.student.school_id, metadata={'student': link.student_id, 'link': link.pk, **changes},
            )
        return Response(self.get_serializer(link).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        from ..tenancy import close_unreachable_direct_chats

        link = self.get_object()
        with transaction.atomic():
            link.status = ParentStudentLink.Status.REVOKED
            link.revoked_at = timezone.now()
            link.save(update_fields=['status', 'revoked_at', 'updated_at'])
            close_unreachable_direct_chats(link.parent)
        return Response(self.get_serializer(link).data)


class ParentPortalView(APIView):
    """The family portal: one payload, a fixed number of queries however many children.

    Each child returns every open task plus the most recent CLOSED_TASKS closed ones, and
    every upcoming meeting plus the most recent PAST_MEETINGS past ones (docs/metrics.md).
    """
    permission_classes = [permissions.IsAuthenticated]
    CLOSED_TASKS = 20
    PAST_MEETINGS = 20
    DECIDED_APPLICATIONS = {Application.Status.ACCEPTED, Application.Status.REJECTED}
    OPEN_MEETINGS = {Booking.Status.PENDING, Booking.Status.APPROVED}

    def get(self, request):
        if request.user.role != User.Role.PARENT:
            return Response({'detail': 'This workspace is only available to parent accounts.'}, status=403)
        visible = parent_visible_links(ParentStudentLink.objects.filter(parent=request.user))
        # Each child counts on its own school's plan; a sibling elsewhere never opens it.
        links = links_with_feature(visible, 'parent_portal').select_related(
            'student__user', 'student__school', 'student__assigned_counselor', 'invited_by'
        )
        pending = links.filter(status=ParentStudentLink.Status.PENDING)
        children = []
        now = timezone.now()
        meetings = Booking.objects.select_related('participant')
        # Hidden sections are prefetched too but never serialized (the can_view_* checks below).
        active_links = list(links.filter(status=ParentStudentLink.Status.ACTIVE).prefetch_related(
            Prefetch('student__tasks', Task.objects.filter(status__in=OPEN_TASK_STATUSES), to_attr='portal_open_tasks'),
            Prefetch(
                'student__tasks',
                Task.objects.exclude(status__in=OPEN_TASK_STATUSES).order_by('-updated_at', '-id')[:self.CLOSED_TASKS],
                to_attr='portal_closed_tasks',
            ),
            Prefetch('student__applications', Application.objects.select_related('university'), to_attr='portal_applications'),
            Prefetch('student__documents', to_attr='portal_documents'),
            Prefetch('student__bookings', meetings.filter(starts_at__gte=now), to_attr='portal_upcoming_meetings'),
            Prefetch(
                'student__bookings', meetings.filter(starts_at__lt=now).order_by('-starts_at')[:self.PAST_MEETINGS],
                to_attr='portal_past_meetings',
            ),
        ))
        attach_progress_stats([link.student for link in active_links])
        for link in active_links:
            student = link.student
            tasks = student.portal_open_tasks + student.portal_closed_tasks
            applications = student.portal_applications if link.can_view_applications else []
            documents = student.portal_documents if link.can_view_documents else []
            meetings = student.portal_upcoming_meetings + student.portal_past_meetings if link.can_view_meetings else []
            children.append({
                'link_id': link.id,
                'relationship': link.relationship,
                'permissions': {
                    'applications': link.can_view_applications,
                    'documents': link.can_view_documents,
                    'meetings': link.can_view_meetings,
                },
                'profile': {
                    'id': student.id,
                    'name': student.user.get_full_name() or student.user.username,
                    'school': student.school.name if student.school else student.school_name,
                    'grade': student.grade,
                    'counselor_name': (
                        student.assigned_counselor.get_full_name() or student.assigned_counselor.username
                        if student.assigned_counselor else None
                    ),
                    'level': student.level,
                    'xp_total': student.xp_total,
                    'next_level_xp': student.next_level_xp,
                    'eligible_level': student.eligible_level,
                    'level_up_pending': student.level_up_pending,
                    'xp_progress_percent': student.xp_progress_percent,
                    'gpa': student.gpa,
                    'ielts_score': student.ielts_score,
                    'sat_score': student.sat_score,
                    'target_major': student.target_major,
                    'target_countries': student.target_countries,
                    'task_progress_percent': student.task_progress_percent,
                    'roadmap_progress_percent': student.roadmap_progress_percent,
                    'journey_progress_percent': student.journey_progress_percent,
                    'is_at_risk': student.is_at_risk,
                    # Headline counts (docs/metrics.md, "Parent portal"); null for a section that is not shared.
                    'open_tasks_total': len(student.portal_open_tasks),
                    'overdue_tasks_total': sum(task.is_overdue for task in student.portal_open_tasks),
                    'active_applications_total': sum(
                        item.status not in self.DECIDED_APPLICATIONS for item in student.portal_applications
                    ) if link.can_view_applications else None,
                    'upcoming_meetings_total': sum(
                        item.status in self.OPEN_MEETINGS and item.starts_at > now for item in student.portal_upcoming_meetings
                    ) if link.can_view_meetings else None,
                },
                'tasks': [{
                    'id': item.id,
                    'title': item.title,
                    'due_date': item.due_date,
                    'priority': item.priority,
                    'status': item.status,
                    'is_overdue': item.is_overdue,
                    'is_self_assigned': item.is_self_assigned,
                } for item in tasks],
                'applications': [{
                    'id': item.id,
                    'university': item.university.name,
                    'country': item.university.country,
                    'program': item.program,
                    'tier': item.tier,
                    'status': item.status,
                    'deadline': item.deadline,
                    'scholarship_deadline': item.scholarship_deadline,
                } for item in applications],
                'documents': [{
                    'id': item.id,
                    'title': item.title,
                    'document_type': item.document_type,
                    'status': item.status,
                    'updated_at': item.updated_at,
                } for item in documents],
                'meetings': [{
                    'id': item.id,
                    'topic': item.topic,
                    'starts_at': item.starts_at,
                    'duration_minutes': item.duration_minutes,
                    'status': item.status,
                    'participant_name': (
                        item.participant.get_full_name() or item.participant.username
                        if item.participant else None
                    ),
                    'participant_role': item.participant.role if item.participant else None,
                    'is_expired': item.is_expired,
                } for item in meetings],
            })
        return Response({
            'children': children,
            'pending_invitations': ParentStudentLinkSerializer(pending, many=True).data,
            'plan_locked_children': visible.filter(status=ParentStudentLink.Status.ACTIVE).count() - len(active_links),
            'privacy': {
                'hidden': ['private essays', 'messages', 'counselor notes', 'task responses', 'document files'],
                'read_only': True,
            },
        })


class StudentParentAccessView(APIView):
    """Read-only: which parents can see the signed-in student's information.

    Students only, and only their own links. Changing what a parent sees is
    done by the counselor; revoked links are left out.
    """

    ALWAYS_VISIBLE = ('profile', 'progress', 'tasks')
    NEVER_VISIBLE = ('private_essays', 'messages', 'counselor_notes', 'task_responses', 'document_files')

    def get(self, request):
        profile = getattr(request.user, 'student_profile', None) if request.user.role == User.Role.STUDENT else None
        if profile is None:
            return Response({'detail': 'Only students can view their parent access.'}, status=403)
        links = ParentStudentLink.objects.filter(
            student=profile,
            status__in=[ParentStudentLink.Status.ACTIVE, ParentStudentLink.Status.PENDING],
        ).select_related('parent').order_by('status', 'parent__first_name', 'parent__last_name', 'id')
        return Response({
            'parents': [{
                'id': link.id,
                'name': link.parent.get_full_name() or link.parent.username,
                'relationship': link.relationship,
                'status': link.status,
                'sections': {
                    'applications': link.can_view_applications,
                    'documents': link.can_view_documents,
                    'meetings': link.can_view_meetings,
                },
                'invited_at': link.invited_at,
                'consented_at': link.consented_at,
            } for link in links],
            'always_visible': list(self.ALWAYS_VISIBLE),
            'never_visible': list(self.NEVER_VISIBLE),
        })
