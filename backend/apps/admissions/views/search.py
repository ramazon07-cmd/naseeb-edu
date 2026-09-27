"""Global header search: the top matches per record type, for this user only.

Every type goes through its own list view's permission classes and
``get_queryset`` (the same scoping as ``/api/<type>/``), so this endpoint can
never show a row the list endpoint would hide. Types a role has no use for
are skipped up front; one LIMITed query per remaining visible type, nothing
is counted.
"""
from django.db.models import F
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User
from apps.users.views import UserViewSet
from ..listing import search_terms
from .catalog import SchoolViewSet
from .essays import EssayViewSet
from .portal import BookingViewSet
from .records import ApplicationViewSet, DocumentViewSet, RecommendationLetterViewSet, TaskViewSet
from .roadmaps import RoadmapMissionViewSet
from .students import StudentProfileViewSet
from .support import SupportTicketViewSet

SEARCH_LIMIT_PER_TYPE = 5
SEARCH_MIN_LENGTH = 2

STUDENT_NAME = ('student__user__first_name', 'student__user__last_name', 'student__user__username')


def _name(first, last, username=''):
    return ' '.join(part for part in (first, last) if part) or username or ''


def _student_name(row):
    return _name(*(row.get(field, '') for field in STUDENT_NAME))


# type -> (viewset, basename, value fields, ordering, row -> (title, subtitle))
SEARCH_TYPES = {
    'students': (
        StudentProfileViewSet, 'students',
        ('user__first_name', 'user__last_name', 'user__username', 'school_name', 'grade'),
        ('user__first_name', 'user__last_name', 'id'),
        lambda row: (_name(row['user__first_name'], row['user__last_name'], row['user__username']), row['school_name']),
    ),
    'tasks': (
        TaskViewSet, 'tasks', ('title', 'status', 'due_date', *STUDENT_NAME), ('due_date', 'id'),
        lambda row: (row['title'], _student_name(row)),
    ),
    'applications': (
        ApplicationViewSet, 'applications', ('program', 'university__name', 'status', *STUDENT_NAME),
        ('-created_at', '-id'),
        lambda row: (row['university__name'] or row['program'], f"{row['program']} · {_student_name(row)}"),
    ),
    'documents': (
        DocumentViewSet, 'documents', ('title', 'status', 'document_type', *STUDENT_NAME), ('-created_at', '-id'),
        lambda row: (row['title'], _student_name(row)),
    ),
    'essays': (
        EssayViewSet, 'essays', ('title', 'status', *STUDENT_NAME), ('-created_at', '-id'),
        lambda row: (row['title'], _student_name(row)),
    ),
    'recommendations': (
        RecommendationLetterViewSet, 'recommendations', ('recommender_name', 'status', *STUDENT_NAME),
        ('-created_at', '-id'),
        lambda row: (row['recommender_name'], _student_name(row)),
    ),
    'roadmapMissions': (
        RoadmapMissionViewSet, 'roadmap-missions', ('title', 'status', *STUDENT_NAME), ('-created_at', '-id'),
        lambda row: (row['title'], _student_name(row)),
    ),
    'bookings': (
        BookingViewSet, 'bookings', ('topic', 'status', 'starts_at', *STUDENT_NAME), ('-starts_at', '-id'),
        lambda row: (row['topic'], _student_name(row)),
    ),
    'schools': (
        SchoolViewSet, 'schools', ('name', 'code', 'workspace_type'), ('name', 'id'),
        lambda row: (row['name'], row['code']),
    ),
    'accounts': (
        UserViewSet, 'accounts', ('first_name', 'last_name', 'username', 'email', 'role'),
        ('first_name', 'last_name', 'id'),
        lambda row: (_name(row['first_name'], row['last_name'], row['username']), row['role']),
    ),
    'supportTickets': (
        SupportTicketViewSet, 'support-tickets', ('subject', 'status', 'category'), ('-updated_at', '-id'),
        lambda row: (row['subject'], row['status']),
    ),
}

STUDENT_RECORD_TYPES = (
    'students', 'tasks', 'applications', 'documents', 'essays', 'recommendations', 'roadmapMissions', 'bookings',
)
# Types worth searching per role, decided before any view is built. This only
# narrows: every type still goes through its list view's permissions and
# scoping. Schools and accounts are admin console pages; other roles find
# people through the (identically scoped) student search. Teachers list only
# students, tasks, missions and bookings; parents have no list endpoints here.
ROLE_SEARCH_TYPES = {
    User.Role.COUNSELOR: (*STUDENT_RECORD_TYPES, 'supportTickets'),
    User.Role.ORGANIZATION: (*STUDENT_RECORD_TYPES, 'supportTickets'),
    User.Role.STUDENT: (*STUDENT_RECORD_TYPES, 'supportTickets'),
    User.Role.TEACHER: ('students', 'tasks', 'roadmapMissions', 'bookings'),
    User.Role.PARENT: (),
}


def search_types_for(user):
    if user.is_product_admin:
        return tuple(SEARCH_TYPES)
    return ROLE_SEARCH_TYPES.get(user.role, ())


def scoped_list_queryset(viewset_class, basename, request):
    """The queryset ``GET /api/<basename>/`` would page through, or None if forbidden."""
    view = viewset_class()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    view.action = 'list'
    view.action_map = {'get': 'list'}
    view.basename = basename
    view.headers = {}
    if not all(permission.has_permission(request, view) for permission in view.get_permissions()):
        return None, view
    return view.get_queryset(), view


class GlobalSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get('q', '')
        terms = search_terms(raw)
        if len(' '.join(terms)) < SEARCH_MIN_LENGTH:
            return Response({'query': raw.strip(), 'results': {}})
        query = ' '.join(terms)
        results = {}
        for key in search_types_for(request.user):
            viewset_class, basename, fields, ordering, describe = SEARCH_TYPES[key]
            queryset, view = scoped_list_queryset(viewset_class, basename, request)
            if queryset is None:
                continue
            queryset = view.apply_search(queryset.prefetch_related(None), query)
            rows = queryset.order_by(*[
                F(term[1:]).desc() if term.startswith('-') else F(term).asc() for term in ordering
            ]).values('id', *fields)[:SEARCH_LIMIT_PER_TYPE]
            items = []
            for row in rows:
                title, subtitle = describe(row)
                items.append({'id': row['id'], 'title': title, 'subtitle': subtitle, 'status': row.get('status', '')})
            if items:
                results[key] = items
        return Response({'query': query, 'results': results})
