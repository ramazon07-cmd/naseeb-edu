"""Admissions API views — common."""
from datetime import timedelta
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from pathlib import Path
import mimetypes
from rest_framework import permissions
from apps.users.models import User
from core.storage import presigned_file_url
from ..models import School, StudentProfile
from ..listing import ListQueryMixin
from ..scoping import scope_students
from ..serializers.common import INLINE_FILE_EXTENSIONS


# Media type of the ``?mode=url`` answer, so a client can tell a link apart
# from the file itself without reading an exposed header.
FILE_LINK_CONTENT_TYPE = 'application/vnd.naseeb.file-link+json'


def serve_private_file(request, field_file, *, original_name='', content_type='', missing_message='The uploaded file is unavailable. Contact support.'):
    """Deliver a private upload to a user the caller has already authorised.

    Inline only for types browsers render safely; ``?download=1`` forces an
    attachment. On object storage the bytes never pass through Django: the
    response is a 302 to a short-lived presigned URL, or with ``?mode=url`` a
    JSON ``{url, expires_at, file_name, content_type}`` for clients that must
    not follow the redirect with their Authorization header. On local disk the
    file is streamed. Responses are never cached and never content-sniffed.
    """
    file_name = original_name or Path(field_file.name).name
    extension = Path(file_name).suffix.lower()
    force_download = request.query_params.get('download') == '1' or extension not in INLINE_FILE_EXTENSIONS
    content_type = content_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
    expire = settings.PRIVATE_FILE_URL_EXPIRE_SECONDS
    url = presigned_file_url(
        field_file, filename=file_name, content_type=content_type, as_attachment=force_download, expire=expire,
    )
    if url:
        if request.query_params.get('mode') == 'url':
            response = JsonResponse(
                {
                    'url': url,
                    'expires_at': (timezone.now() + timedelta(seconds=expire)).isoformat(),
                    'file_name': file_name,
                    'content_type': content_type,
                },
                content_type=FILE_LINK_CONTENT_TYPE,
            )
        else:
            response = HttpResponseRedirect(url)
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'
        return response
    try:
        stream = field_file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404(missing_message)
    response = FileResponse(
        stream,
        as_attachment=force_download,
        filename=file_name,
        content_type=content_type,
    )
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class CounselorOrOwnerPermission(permissions.BasePermission):
    organization_read_resources = {
        'tasks', 'applications', 'documents', 'essays', 'achievements',
        'researches', 'projects', 'internships', 'activities',
        'honors', 'recommendations',
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_counselor_like:
            return True
        if user.role == User.Role.TEACHER:
            return bool(
                view.basename == 'students'
                and (request.method in permissions.SAFE_METHODS or view.action == 'approve_level')
            )
        if user.is_organization:
            if view.basename == 'schools':
                return request.method in permissions.SAFE_METHODS
            if view.basename == 'students':
                return True
            return (
                request.method in permissions.SAFE_METHODS
                and view.basename in self.organization_read_resources
            )
        if request.method in permissions.SAFE_METHODS:
            return True
        if view.basename == 'notifications' and view.action in {'read', 'read_all'}:
            return True
        if view.basename == 'students':
            return view.action in {'update', 'partial_update', 'onboarding', 'photo'}
        if view.basename == 'tasks' and view.action == 'create':
            return False
        return view.basename in {
            'applications', 'documents', 'essays', 'tasks', 'achievements', 'researches', 'projects',
            'internships', 'activities', 'honors', 'recommendations',
        }

    def has_object_permission(self, request, view, obj):
        if request.user.is_counselor_like:
            return True
        if request.user.role == User.Role.TEACHER:
            student = obj if isinstance(obj, StudentProfile) else getattr(obj, 'student', None)
            return bool(
                (request.method in permissions.SAFE_METHODS or view.action == 'approve_level')
                and isinstance(student, StudentProfile)
                and request.user.school_id
                and student.school_id == request.user.school_id
            )
        if isinstance(obj, School) and request.user.is_organization:
            return request.method in permissions.SAFE_METHODS and obj.id == request.user.school_id
        student = getattr(obj, 'student', obj if isinstance(obj, StudentProfile) else None)
        if request.user.is_organization:
            owns_student = bool(
                isinstance(student, StudentProfile)
                and request.user.school_id
                and student.school_id == request.user.school_id
            )
            if not owns_student:
                return False
            if view.basename == 'students':
                return True
            return request.method in permissions.SAFE_METHODS
        if student and getattr(student, 'user_id', None) == request.user.id:
            if view.basename == 'notifications' and view.action == 'read':
                return True
            if view.basename == 'students':
                return view.action in {'retrieve', 'update', 'partial_update', 'photo'}
            return request.method in permissions.SAFE_METHODS or view.basename in {
                'applications', 'documents', 'essays', 'tasks', 'achievements', 'researches', 'projects',
                'internships', 'activities', 'honors', 'recommendations',
            }
        return False


class ScopedQuerysetMixin:
    permission_classes = [CounselorOrOwnerPermission]
    # A model without a student link has no tenant to scope by. Such a viewset
    # gets nothing unless it opts in, and then it must scope the rows itself.
    allow_unscoped_records = False

    def filter_for_user(self, queryset):
        if queryset.model == StudentProfile:
            return scope_students(queryset, self.request.user)
        if hasattr(queryset.model, 'student'):
            return scope_students(queryset, self.request.user, via='student')
        if self.allow_unscoped_records:
            return queryset
        return queryset.none()


RECORD_ORDERING = {
    '-created': ('-created_at', '-id'),
    'created': ('created_at', 'id'),
    '-updated': ('-updated_at', '-id'),
}


class StudentRecordListMixin(ListQueryMixin):
    """List contract for per-student records (tasks, applications, portfolio…).

    Filters always narrow the caller's scoped queryset; they never widen it.
    """

    search_student_path = 'student'
    int_filters = {
        'student': 'student_id',
        'school': 'student__school_id',
        'counselor': 'student__assigned_counselor_id',
    }
    date_filters = {'created': 'created_at', 'updated': 'updated_at'}
    ordering_options = RECORD_ORDERING
    default_cursor_ordering = '-created'


# Upper bounds for list-shaped custom actions.
CONTACT_LIST_LIMIT = 500
COLLEGE_RESEARCH_LIMIT = 50
SCREEN_TIME_TEAM_LIMIT = 200


class StaffControlledWorkPermission(permissions.BasePermission):
    """Managers assign scoped work; students may create personal zero-XP tasks."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_task_manager:
            return user.role != User.Role.TEACHER or bool(user.school_id)
        if user.is_organization:
            return view.basename in {'tasks', 'roadmap-missions'} and request.method in permissions.SAFE_METHODS
        if user.role == User.Role.STUDENT:
            if request.method in permissions.SAFE_METHODS:
                return True
            if view.action in {'create', 'destroy'}:
                return view.basename == 'tasks'
            return view.action in {'update', 'partial_update', 'onboarding'}
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        student = obj.student
        if user.is_counselor_like:
            return True
        if user.role == User.Role.TEACHER:
            return bool(user.school_id and student.school_id == user.school_id)
        if user.is_organization:
            return bool(
                request.method in permissions.SAFE_METHODS
                and user.school_id
                and student.school_id == user.school_id
            )
        if student.user_id != user.id:
            return False
        if request.method in permissions.SAFE_METHODS or view.action in {'update', 'partial_update'}:
            return True
        return view.action == 'destroy' and obj.is_self_assigned


class StaffControlledWorkMixin:
    permission_classes = [StaffControlledWorkPermission]

    def filter_work_for_user(self, queryset):
        return scope_students(queryset, self.request.user, via='student')


class ProductAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_product_admin)
