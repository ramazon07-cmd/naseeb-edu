"""Student-only Essay Lab API (`/api/essay-lab/`).

Ownership is enforced in every queryset (`student__user=request.user`), so
another student's ids behave exactly like missing ids (404); tab ids are only
ever looked up inside the student's essay. An essay is a document of ordered
tabs. A tab's text only changes through `autosave` and checkpoint `restore`,
which lock the essay row (serializing all writes to one document) and use the
tab's `save_seq` counter for optimistic concurrency.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import BooleanField, Case, Count, ExpressionWrapper, IntegerField, Max, Q, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import exceptions, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.settings import api_settings

from apps.users.audit import audit_product_action
from apps.users.entitlements import require_feature
from apps.users.models import User
from ..models import (
    ActivityLog, Essay, EssayCheckpoint, EssayDepthCheck, EssayFolder, EssayRevision, EssayTab, Notification,
    StudentProfile,
)
from ..streaming import release_db_connection
from . import coach
from .doc import DocError, apply_delta, doc_from_text, doc_hash, doc_stats, tab_doc, validate_doc
from .serializers import (
    SUMMARY_FIELDS,
    AutosaveSerializer,
    BaseSeqSerializer,
    CheckpointCreateSerializer,
    CheckpointDetailSerializer,
    CheckpointSummarySerializer,
    DepthCheckSerializer,
    EssayDetailSerializer,
    EssayDuplicateSerializer,
    EssayMetadataSerializer,
    EssaySummarySerializer,
    FolderOrderSerializer,
    FolderSerializer,
    FolderWriteSerializer,
    TabCreateSerializer,
    TabDetailSerializer,
    TabMetaSerializer,
    TabOrderSerializer,
    TabQuerySerializer,
    TabRenameSerializer,
)
from .tabs import (
    FIRST_TAB_TITLE, MAX_TAB_TITLE, MAX_TABS, ensure_first_tab, refresh_essay_text, shift_after, tab_from_text,
    tree_order,
)
from .throttles import EssayAutosaveThrottle, EssayDepthCheckThrottle, spend_coach_budget

LIST_LIMIT = 500
CHECKPOINT_CAP = 200
CHECKPOINT_LIST_LIMIT = 200
DEPTH_CHECK_KEEP = 20
AUTO_CHECKPOINT_INTERVAL = timedelta(minutes=10)
MAX_FOLDERS = 200
DEFAULT_TITLE = 'Untitled essay'


class EssayLabError(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Request could not be completed.'
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if status_code:
            self.status_code = status_code
        super().__init__(detail, code)


class SlowDown(exceptions.Throttled):
    default_detail = 'You are going a little fast. Please wait a moment and try again.'
    default_code = 'slow_down'


class IsStudent(permissions.BasePermission):
    message = 'The Essay Lab is available to students only.'
    code = 'students_only'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.STUDENT)


def error(detail, code, http_status, **extra):
    return Response({'detail': detail, 'code': code, **extra}, status=http_status)


class EssayLabViewMixin:
    permission_classes = [permissions.IsAuthenticated, IsStudent]
    pagination_class = None
    lookup_value_regex = '[0-9]+'

    def get_throttles(self):
        throttle_classes = getattr(self, 'action_throttles', {}).get(self.action)
        if throttle_classes is None:
            throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES
        return [throttle() for throttle in throttle_classes]

    def throttled(self, request, wait):
        raise SlowDown(wait=wait)

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        data = response.data
        if isinstance(exc, exceptions.ValidationError):
            first = data
            while isinstance(first, (list, dict)) and first:
                first = next(iter(first.values())) if isinstance(first, dict) else first[0]
            response.data = {'detail': str(first or 'Invalid request.'), 'code': 'invalid', 'errors': data}
        elif isinstance(data, dict) and 'detail' in data and 'code' not in data:
            codes = exc.get_codes() if isinstance(exc, exceptions.APIException) else None
            data['code'] = codes if isinstance(codes, str) else 'error'
        return response

    def student_id(self):
        """The requesting student's profile id (one query, cached per request)."""
        if not hasattr(self, '_student_id'):
            self._student_id = (
                StudentProfile.objects.filter(user=self.request.user).values_list('id', flat=True).first()
            )
            if self._student_id is None:
                raise EssayLabError('Finish creating your student profile first.', 'profile_missing', 403)
        return self._student_id

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in self.student_context_actions and self.request.method != 'GET':
            context['student_id'] = self.student_id()
        return context


def _essays_for(user):
    return Essay.objects.filter(student__user=user)


def _prune_checkpoints(essay_id):
    """Keep at most CHECKPOINT_CAP checkpoints per document, dropping the oldest automatic ones first.

    One DELETE ... WHERE id IN (everything past the CAP newest-to-keep rows); checkpoints have no dependents.
    """
    beyond_cap = (
        EssayCheckpoint.objects.filter(essay_id=essay_id)
        .annotate(keep_rank=Case(When(reason=EssayCheckpoint.Reason.AUTO, then=Value(0)), default=Value(1),
                                 output_field=IntegerField()))
        .order_by('-keep_rank', '-created_at', '-id')
        .values('id')[CHECKPOINT_CAP:]
    )
    EssayCheckpoint.objects.filter(id__in=beyond_cap).delete()


def _make_checkpoint(essay, tab, reason, label=''):
    """Snapshot the tab's current text."""
    checkpoint = EssayCheckpoint.objects.create(
        essay_id=essay.pk,
        tab=tab,
        doc=tab_doc(tab),
        content=tab.content,
        word_count=tab.word_count,
        reason=reason,
        label=label,
    )
    _prune_checkpoints(essay.pk)
    return checkpoint


def _saved_at(tab):
    return serializers.DateTimeField().to_representation(tab.last_edited_at or tab.updated_at)


def _conflict(tab):
    return error(
        'This essay changed somewhere else. Load the latest version or keep yours.',
        'conflict',
        status.HTTP_409_CONFLICT,
        tab=tab.pk,
        save_seq=tab.save_seq,
        doc=tab_doc(tab),
        saved_at=_saved_at(tab),
    )


def _resync(tab, doc):
    """The delta didn't apply to the stored doc: the client resends the whole doc."""
    return error(
        'Your changes need a full save.',
        'resync',
        status.HTTP_409_CONFLICT,
        tab=tab.pk,
        save_seq=tab.save_seq,
        doc=doc,
        saved_at=_saved_at(tab),
    )


def _set_text(tab, doc, stats):
    tab.doc = doc
    tab.content = stats.content
    tab.word_count = stats.word_count
    tab.char_count = stats.char_count
    tab.char_count_no_spaces = stats.char_count_no_spaces


TEXT_FIELDS = ['doc', 'content', 'word_count', 'char_count', 'char_count_no_spaces']


def _tab_metas(essay_id):
    return list(EssayTab.objects.filter(essay_id=essay_id).only(*TAB_META_ONLY))


# `only()` names for the tab rail (the doc and text stay in the database).
TAB_META_ONLY = (
    'id', 'essay', 'parent', 'title', 'position', 'word_count', 'char_count', 'char_count_no_spaces', 'save_seq',
    'last_edited_at', 'updated_at',
)


class EssayLabEssayViewSet(EssayLabViewMixin, viewsets.GenericViewSet):
    serializer_class = EssayDetailSerializer
    student_context_actions = {'create', 'partial_update', 'duplicate'}
    action_throttles = {
        'autosave': [EssayAutosaveThrottle],
        # Counted inside the action, after the stale/empty checks, so a rejected
        # request doesn't use up the student's 15-second slot.
        'depth_check': [],
    }

    def get_queryset(self):
        return _essays_for(self.request.user)

    def get_essay(self, pk, *, allow_trashed=False, lock=False, defer=()):
        queryset = self.get_queryset()
        if not allow_trashed:
            queryset = queryset.filter(trashed_at__isnull=True)
        if lock:
            # `of=('self',)` keeps PostgreSQL from also locking the joined student row.
            queryset = queryset.select_for_update(of=('self',))
        if defer:
            queryset = queryset.defer(*defer)
        # order_by() drops the model's default ordering, which would join the user table.
        essay = queryset.filter(pk=pk).order_by().first()
        if essay is None:
            raise exceptions.NotFound('Essay not found.')
        return essay

    def resolve_tab(self, essay, tab_id, *, lock=False, with_doc=True):
        """The tab `tab_id` of this essay (404 for any other id).

        Without an id (older clients) the document must have exactly one tab.
        An essay made outside the Essay Lab gets its first tab here.
        """
        queryset = EssayTab.objects.filter(essay_id=essay.pk)
        if lock:
            queryset = queryset.select_for_update()
        if not with_doc:
            queryset = queryset.defer('doc')
        if tab_id is not None:
            tab = queryset.filter(pk=tab_id).first()
            if tab is None:
                raise exceptions.NotFound('Tab not found.')
            return tab
        tabs = list(queryset.order_by('position', 'id')[:2])
        if len(tabs) > 1:
            raise EssayLabError('Say which tab this is for.', 'tab_required')
        if tabs:
            return tabs[0]
        with transaction.atomic():
            ensure_first_tab(essay)
        return queryset.get()

    def detail_response(self, essay, active_id=None, status_code=status.HTTP_200_OK):
        """The document with every tab's metadata and one tab's doc (3 queries at most, bar a concurrent delete)."""
        for _attempt in range(2):
            metas = _tab_metas(essay.pk)
            if not metas:
                with transaction.atomic():
                    ensure_first_tab(essay)
                metas = _tab_metas(essay.pk)
            if not metas:
                break
            ordered = tree_order(metas)
            active = next((tab for tab in ordered if tab.pk == active_id), ordered[0])
            tab = EssayTab.objects.filter(pk=active.pk).first()
            if tab is not None:
                data = EssayDetailSerializer(essay, context={'tabs': ordered, 'tab': tab}).data
                return Response(data, status=status_code)
            # The tab was deleted after the list was read: list again and open another one.
        raise exceptions.NotFound('Tab not found.')

    # ------------------------------------------------------------------ library

    def list(self, request):
        queryset = self.get_queryset().only(*SUMMARY_FIELDS)
        params = request.query_params
        trashed = params.get('trashed', '0')
        if trashed not in {'0', '1'}:
            raise EssayLabError('trashed must be 0 or 1.', 'invalid_filter')
        queryset = queryset.filter(trashed_at__isnull=(trashed == '0'))
        folder = params.get('folder')
        if folder == 'none':
            queryset = queryset.filter(folder__isnull=True)
        elif folder:
            if not folder.isdigit():
                raise EssayLabError('folder must be a folder id or "none".', 'invalid_filter')
            queryset = queryset.filter(folder_id=int(folder))
        essay_type = params.get('type')
        if essay_type:
            if essay_type not in Essay.EssayType.values:
                raise EssayLabError('Unknown essay type.', 'invalid_filter')
            queryset = queryset.filter(essay_type=essay_type)
        query = (params.get('q') or '').strip()[:120]
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(prompt__icontains=query) | Q(university_name__icontains=query)
                | Q(content__icontains=query)
            )
        queryset = queryset.order_by('-updated_at', '-id')[:LIST_LIMIT]
        return Response(EssaySummarySerializer(queryset, many=True).data)

    def create(self, request):
        serializer = EssayMetadataSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        now = timezone.now()
        with transaction.atomic():
            essay = Essay.objects.create(
                student_id=self.student_id(),
                title=values.get('title') or DEFAULT_TITLE,
                essay_type=values.get('essay_type', Essay.EssayType.PERSONAL_STATEMENT),
                prompt=values.get('prompt', ''),
                university_name=values.get('university_name', ''),
                word_limit=values.get('word_limit'),
                folder=values.get('folder'),
                page_size=values.get('page_size', Essay.PageSize.A4),
                last_edited_at=now,
            )
            tab = EssayTab.objects.create(
                essay=essay, title=values.get('first_tab_title') or FIRST_TAB_TITLE, position=0,
                doc=doc_from_text(''), last_edited_at=now,
            )
            # Same first revision the legacy API creates, so counselor history starts at v1.
            EssayRevision.objects.create(
                essay=essay, version=essay.version, prompt=essay.prompt, content='',
                status=essay.status, created_by=request.user,
            )
        data = EssayDetailSerializer(essay, context={'tabs': [tab], 'tab': tab}).data
        return Response(data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        essay = self.get_essay(pk, allow_trashed=True)
        query = TabQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        # A stale tab id (deleted on another device) opens the first tab instead.
        return self.detail_response(essay, query.validated_data.get('tab'))

    def partial_update(self, request, pk=None):
        essay = self.get_essay(pk)
        serializer = EssayMetadataSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        values.pop('first_tab_title', None)
        if 'title' in values and not values['title']:
            values['title'] = DEFAULT_TITLE
        if values:
            for field, value in values.items():
                setattr(essay, field, value)
            # Metadata never touches the tabs' text, so no lock is needed.
            essay.save(update_fields=[*values.keys(), 'updated_at'])
        return Response(EssaySummarySerializer(essay).data)

    def update(self, request, pk=None):
        raise exceptions.MethodNotAllowed('PUT')

    def destroy(self, request, pk=None):
        essay = self.get_essay(pk, allow_trashed=True)
        if essay.trashed_at is None:
            raise EssayLabError('Move the essay to the trash before deleting it.', 'not_trashed', 409)
        essay.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def trash(self, request, pk=None):
        essay = self.get_essay(pk, allow_trashed=True)
        if essay.trashed_at is None:
            essay.trashed_at = timezone.now()
            essay.save(update_fields=['trashed_at', 'updated_at'])
        return Response(EssaySummarySerializer(essay).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        essay = self.get_essay(pk, allow_trashed=True)
        if essay.trashed_at is not None:
            essay.trashed_at = None
            essay.save(update_fields=['trashed_at', 'updated_at'])
        return Response(EssaySummarySerializer(essay).data)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        source = self.get_essay(pk)
        serializer = EssayDuplicateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        tabs = tree_order(list(EssayTab.objects.filter(essay_id=source.pk)))
        now = timezone.now()
        with transaction.atomic():
            essay = Essay.objects.create(
                student_id=source.student_id,
                title=values.get('title') or f'{source.title} (copy)'[:220],
                essay_type=source.essay_type,
                prompt=source.prompt,
                university_name=values.get('university_name', source.university_name),
                word_limit=source.word_limit,
                folder=values['folder'] if 'folder' in values else source.folder,
                page_size=source.page_size,
                content=source.content,
                last_edited_at=now,
            )
            if tabs:
                # A new row is counted from its plain text; the copied tabs decide the real counts.
                refresh_essay_text(essay, tabs=_copy_tabs(essay, tabs, now))
            else:
                tab_from_text(essay, source.content).save()
            EssayRevision.objects.create(
                essay=essay, version=essay.version, prompt=essay.prompt, content=essay.content,
                status=essay.status, created_by=request.user,
            )
        return self.detail_response(essay, status_code=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------- tabs

    @action(detail=True, methods=['post'], url_path='tabs')
    def tabs_create(self, request, pk=None):
        serializer = TabCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        now = timezone.now()
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            metas = _tab_metas(essay.pk) or [ensure_first_tab(essay)]
            if len(metas) >= MAX_TABS:
                raise EssayLabError(f'A document can have up to {MAX_TABS} tabs.', 'too_many_tabs', 409)
            parent_id = values.get('parent')
            if parent_id is not None:
                parent = next((tab for tab in metas if tab.pk == parent_id), None)
                if parent is None:
                    raise EssayLabError('That tab is not in this document.', 'invalid_tab')
                if parent.parent_id is not None:
                    raise EssayLabError('Sub-tabs can’t have their own sub-tabs.', 'nesting_limit')
            positions = [tab.position for tab in metas if tab.parent_id == parent_id]
            tab = EssayTab.objects.create(
                essay_id=essay.pk, parent_id=parent_id, title=values.get('title') or f'Tab {len(metas) + 1}',
                position=max(positions) + 1 if positions else 0, doc=doc_from_text(''), last_edited_at=now,
            )
            refresh_essay_text(essay)
        return Response({'tab': TabDetailSerializer(tab).data,
                         'tabs': TabMetaSerializer(tree_order([*metas, tab]), many=True).data},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'patch', 'delete'], url_path=r'tabs/(?P<tid>[0-9]+)')
    def tab_detail(self, request, pk=None, tid=None):
        if request.method == 'GET':
            essay = self.get_essay(pk, allow_trashed=True, defer=('content',))
            return Response(TabDetailSerializer(self.resolve_tab(essay, int(tid))).data)
        if request.method == 'PATCH':
            serializer = TabRenameSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                essay = self.get_essay(pk, lock=True, defer=('content',))
                tab = self.resolve_tab(essay, int(tid), lock=True, with_doc=False)
                if tab.title != serializer.validated_data['title']:
                    tab.title = serializer.validated_data['title']
                    tab.save(update_fields=['title', 'updated_at'])
                    refresh_essay_text(essay)
            return Response(TabMetaSerializer(tab).data)
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            metas = _tab_metas(essay.pk)
            tab = next((item for item in metas if item.pk == int(tid)), None)
            if tab is None:
                raise exceptions.NotFound('Tab not found.')
            remaining = [item for item in metas if item.pk != tab.pk and item.parent_id != tab.pk]
            if not remaining:
                raise EssayLabError('A document needs at least one tab.', 'last_tab', 409)
            # Sub-tabs, checkpoints and Coach checks go with it (CASCADE).
            EssayTab.objects.filter(pk=tab.pk).delete()
            refresh_essay_text(essay)
        return Response({'tabs': TabMetaSerializer(tree_order(remaining), many=True).data,
                         'word_count': essay.word_count})

    @action(detail=True, methods=['post'], url_path=r'tabs/(?P<tid>[0-9]+)/duplicate')
    def tab_duplicate(self, request, pk=None, tid=None):
        now = timezone.now()
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            metas = _tab_metas(essay.pk)
            source = next((item for item in metas if item.pk == int(tid)), None)
            if source is None:
                raise exceptions.NotFound('Tab not found.')
            family = [source.pk, *(item.pk for item in metas if item.parent_id == source.pk)]
            if len(metas) + len(family) > MAX_TABS:
                raise EssayLabError(f'A document can have up to {MAX_TABS} tabs.', 'too_many_tabs', 409)
            originals = tree_order(list(EssayTab.objects.filter(pk__in=family)))
            shift_after(essay.pk, source.parent_id, source.position)
            copy_title = f'{source.title} (copy)'[:MAX_TAB_TITLE]
            copies = _copy_tabs(essay, originals, now, position=source.position + 1, first_title=copy_title)
            refresh_essay_text(essay)
        return Response({'tab': TabDetailSerializer(copies[0]).data,
                         'tabs': TabMetaSerializer(tree_order(_tab_metas(essay.pk)), many=True).data},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'], url_path='tabs/order')
    def tabs_order(self, request, pk=None):
        serializer = TabOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent_id = serializer.validated_data['parent']
        ids = serializer.validated_data['ids']
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            siblings = {
                tab.pk: tab for tab in EssayTab.objects.select_for_update().filter(essay_id=essay.pk, parent_id=parent_id)
                .only('id', 'position')
            }
            if not ids or len(ids) != len(set(ids)) or set(ids) != set(siblings):
                raise EssayLabError('Send every tab of this level exactly once.', 'order_mismatch')
            for position, tab_id in enumerate(ids):
                siblings[tab_id].position = position
            EssayTab.objects.bulk_update(siblings.values(), ['position'])
            refresh_essay_text(essay)
        return Response({'tabs': TabMetaSerializer(tree_order(_tab_metas(essay.pk)), many=True).data})

    # ------------------------------------------------------------------ sharing

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        return self._set_shared(pk, True)

    @action(detail=True, methods=['post'])
    def unshare(self, request, pk=None):
        return self._set_shared(pk, False)

    def _set_shared(self, pk, shared):
        """Idempotent: repeating a share or unshare changes and records nothing."""
        with transaction.atomic():
            essay = (
                self.get_queryset().filter(pk=pk)
                .select_related('student__user')
                .select_for_update(of=('self',))
                .only(*SUMMARY_FIELDS, 'student__user_id', 'student__school_id', 'student__assigned_counselor_id',
                      'student__user__first_name', 'student__user__last_name', 'student__user__username')
                .order_by().first()
            )
            if essay is None:
                raise exceptions.NotFound('Essay not found.')
            if essay.shared_with_counselor != shared:
                # Sharing is not an edit, so updated_at (the library order) stays put.
                essay.shared_with_counselor = shared
                essay.shared_at = timezone.now() if shared else None
                Essay.objects.filter(pk=essay.pk).update(
                    shared_with_counselor=essay.shared_with_counselor, shared_at=essay.shared_at,
                )
                self._record_sharing(essay, shared)
        return Response(EssaySummarySerializer(essay).data)

    def _record_sharing(self, essay, shared):
        # Neither the log nor the notice names the essay: both stay readable after an unshare.
        student = essay.student
        event = 'essay.shared' if shared else 'essay.unshared'
        ActivityLog.objects.create(
            actor=self.request.user, student=student,
            action='Essay shared with counselor' if shared else 'Essay no longer shared with counselor',
            metadata={'event': event, 'essay': essay.pk},
        )
        audit_product_action(actor=self.request.user, action=event, target=student, metadata={'essay': essay.pk})
        if shared and student.assigned_counselor_id:
            name = student.user.get_full_name() or student.user.username
            Notification.objects.create(
                student=student, title='Essay shared with counselor', message=f'{name} shared an essay for review.',
                kind=Notification.Kind.ESSAY, target_id=essay.pk,
            )

    # ----------------------------------------------------------------- autosave

    @action(detail=True, methods=['put'])
    def autosave(self, request, pk=None):
        serializer = AutosaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        is_delta = 'ops' in values
        if not is_delta:
            # Validate and derive before taking the row locks, so they are held briefly.
            try:
                doc = validate_doc(values['doc'])
            except DocError as exc:
                return error(exc.detail, exc.code, exc.status)
            stats = doc_stats(doc)
            saved_hash = doc_hash(doc)

        with transaction.atomic():
            # The essay row lock serializes every write to this document's tabs,
            # so the essay's derived text always matches them.
            essay = self.get_essay(pk, lock=True, defer=('content',))
            # A delta needs the stored doc; a full save never reads it.
            tab = self.resolve_tab(essay, values.get('tab'), lock=True, with_doc=is_delta)
            if values['client_save_id'] == tab.last_client_save_id:
                # A retry of a save that already landed.
                return Response({'tab': tab.pk, 'save_seq': tab.save_seq, 'saved_at': _saved_at(tab),
                                 'word_count': tab.word_count})
            if values['base_seq'] != tab.save_seq:
                return _conflict(tab)
            if is_delta:
                stored = tab_doc(tab)
                try:
                    doc, saved_hash = apply_delta(stored, values['ops'], values['doc_hash'])
                except DocError as exc:
                    if exc.code == 'resync':
                        return _resync(tab, stored)
                    return error(exc.detail, exc.code, exc.status)
                if doc == stored:
                    # Nothing changed: no write, no new seq.
                    return Response({'tab': tab.pk, 'save_seq': tab.save_seq, 'saved_at': _saved_at(tab),
                                     'word_count': tab.word_count, 'doc_hash': saved_hash})
                stats = doc_stats(doc)

            latest = (
                EssayCheckpoint.objects.filter(tab_id=tab.pk)
                .annotate(same_text=ExpressionWrapper(Q(content=stats.content), output_field=BooleanField()))
                .order_by('-created_at', '-id')
                .values('created_at', 'same_text')
                .first()
            )
            now = timezone.now()
            text_changed = stats.content != tab.content
            _set_text(tab, doc, stats)
            tab.save_seq += 1
            tab.last_client_save_id = values['client_save_id']
            tab.last_edited_at = now
            update_fields = [*TEXT_FIELDS, 'save_seq', 'last_client_save_id', 'last_edited_at', 'updated_at']
            if 'cursor' in values:
                tab.last_cursor = values['cursor']
                update_fields.append('last_cursor')
            tab.save(update_fields=update_fields)
            if text_changed:
                refresh_essay_text(essay, now=now)
            else:
                essay.last_edited_at = now
                essay.save(update_fields=['last_edited_at', 'updated_at'])

            due = latest is None or (latest['created_at'] <= now - AUTO_CHECKPOINT_INTERVAL and not latest['same_text'])
            if due and stats.content.strip():
                _make_checkpoint(essay, tab, EssayCheckpoint.Reason.AUTO)
        # The client bases its next delta on this save only when this hash matches its own.
        return Response({
            'tab': tab.pk, 'save_seq': tab.save_seq, 'saved_at': _saved_at(tab), 'word_count': stats.word_count,
            'char_count': stats.char_count, 'char_count_no_spaces': stats.char_count_no_spaces,
            'doc_hash': saved_hash, 'document_word_count': essay.word_count,
        })

    # -------------------------------------------------------------- checkpoints

    @action(detail=True, methods=['get', 'post'])
    def checkpoints(self, request, pk=None):
        if request.method == 'GET':
            query = TabQuerySerializer(data=request.query_params)
            query.is_valid(raise_exception=True)
            essay = self.get_essay(pk, allow_trashed=True, defer=('content',))
            tab = self.resolve_tab(essay, query.validated_data.get('tab'), with_doc=False)
            queryset = EssayCheckpoint.objects.filter(essay_id=essay.pk, tab_id=tab.pk).only(
                'id', 'tab', 'reason', 'label', 'word_count', 'created_at',
            )
            return Response(CheckpointSummarySerializer(queryset[:CHECKPOINT_LIST_LIMIT], many=True).data)
        serializer = CheckpointCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            tab = self.resolve_tab(essay, serializer.validated_data.get('tab'), lock=True)
            checkpoint = _make_checkpoint(
                essay, tab, EssayCheckpoint.Reason.MANUAL, label=serializer.validated_data.get('label', ''),
            )
        return Response(CheckpointSummarySerializer(checkpoint).data, status=status.HTTP_201_CREATED)

    def _checkpoint(self, essay, cid):
        checkpoint = EssayCheckpoint.objects.filter(essay_id=essay.pk, pk=cid).first()
        if checkpoint is None:
            raise exceptions.NotFound('Checkpoint not found.')
        return checkpoint

    @action(detail=True, methods=['get'], url_path=r'checkpoints/(?P<cid>[0-9]+)')
    def checkpoint_detail(self, request, pk=None, cid=None):
        essay = self.get_essay(pk, allow_trashed=True, defer=('content',))
        return Response(CheckpointDetailSerializer(self._checkpoint(essay, cid)).data)

    @action(detail=True, methods=['post'], url_path=r'checkpoints/(?P<cid>[0-9]+)/restore')
    def checkpoint_restore(self, request, pk=None, cid=None):
        serializer = BaseSeqSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            checkpoint = self._checkpoint(essay, cid)
            # A checkpoint always restores into the tab it was taken from.
            tab = self.resolve_tab(essay, checkpoint.tab_id, lock=True)
            if serializer.validated_data['base_seq'] != tab.save_seq:
                return _conflict(tab)
            _make_checkpoint(essay, tab, EssayCheckpoint.Reason.RESTORE, label=f'Before restoring #{checkpoint.pk}')
            now = timezone.now()
            _set_text(tab, checkpoint.doc, doc_stats(checkpoint.doc))
            tab.save_seq += 1
            tab.last_edited_at = now
            tab.save(update_fields=[*TEXT_FIELDS, 'save_seq', 'last_edited_at', 'updated_at'])
            refresh_essay_text(essay, now=now)
        return Response({**TabDetailSerializer(tab).data, 'document_word_count': essay.word_count})

    # -------------------------------------------------------------- depth check

    @action(detail=True, methods=['post'], url_path='depth-check')
    def depth_check(self, request, pk=None):
        serializer = BaseSeqSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        essay = self.get_essay(pk, defer=('content',))
        # The Coach reads the open tab. Its doc is loaded now (not deferred) so the
        # checkpoint below snapshots exactly the text that was checked, even if an
        # autosave lands during the AI call.
        tab = self.resolve_tab(essay, serializer.validated_data.get('tab'))
        if serializer.validated_data['base_seq'] != tab.save_seq:
            return error('Save your latest changes before the check.', 'stale', status.HTTP_409_CONFLICT,
                         save_seq=tab.save_seq)
        if not tab.content.strip():
            raise EssayLabError('Write something first, then ask the Coach.', 'empty_essay')
        require_feature(request, 'essay_coach')
        throttle = EssayDepthCheckThrottle()
        if not throttle.allow_request(request, self):
            self.throttled(request, throttle.wait())

        # The AI call runs outside any transaction so no row lock is held while waiting on it.
        if coach.gateway_configured():
            if not spend_coach_budget(request.user):
                raise EssayLabError('The Coach is resting for today. Please try again tomorrow.', 'coach_resting', 503)
            release_db_connection()  # don't hold a pooled connection during the AI call
            try:
                result, model = coach.run_ai_check(essay, tab.content)
            except coach.CoachUnavailable:
                raise EssayLabError('The Coach is unavailable right now. Please try again soon.',
                                    'coach_unavailable', 503)
        else:
            result, model = coach.run_local_check(essay, tab.content)

        with transaction.atomic():
            # The tab (or the essay) may have been deleted during the AI call.
            essay = self.get_essay(pk, lock=True, defer=('content',))
            if not EssayTab.objects.filter(pk=tab.pk, essay_id=essay.pk).exists():
                raise exceptions.NotFound('Tab not found.')
            check = EssayDepthCheck.objects.create(essay_id=essay.pk, tab=tab, save_seq=tab.save_seq, result=result,
                                                   model=model)
            stale_ids = list(
                EssayDepthCheck.objects.filter(tab_id=tab.pk).order_by('-created_at', '-id')
                .values_list('id', flat=True)[DEPTH_CHECK_KEEP:]
            )
            if stale_ids:
                EssayDepthCheck.objects.filter(id__in=stale_ids).delete()
            _make_checkpoint(essay, tab, EssayCheckpoint.Reason.DEPTH_CHECK, label='Coach check')
        return Response(DepthCheckSerializer(check).data)

    @action(detail=True, methods=['get'], url_path='depth-check/latest')
    def depth_check_latest(self, request, pk=None):
        query = TabQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        essay = self.get_essay(pk, allow_trashed=True, defer=('content',))
        checks = EssayDepthCheck.objects.filter(essay_id=essay.pk)
        if 'tab' in query.validated_data:
            checks = checks.filter(tab_id=self.resolve_tab(essay, query.validated_data['tab'], with_doc=False).pk)
        # Without a tab (the library card): the document's latest check, whichever tab it read.
        check = checks.order_by('-created_at', '-id').first()
        if check is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(DepthCheckSerializer(check).data)


def _copy_tabs(essay, originals, now, *, position=None, first_title=None):
    """Copy tabs (in reading order, parents before their sub-tabs) into `essay`.

    With `position`, the first tab becomes a sibling of its original at that
    position (duplicating one tab); otherwise the positions are kept (duplicating
    a whole document). Returns the copies in the same order.
    """
    copies = []
    new_parent = {}
    original_ids = {tab.pk for tab in originals}
    top = [tab for tab in originals if tab.parent_id not in original_ids]
    for index, tab in enumerate(top):
        copies.append(EssayTab(
            essay_id=essay.pk, parent_id=tab.parent_id if position is not None else None,
            title=first_title if index == 0 and first_title else tab.title,
            position=position if position is not None and index == 0 else tab.position,
            doc=tab.doc, content=tab.content, word_count=tab.word_count, char_count=tab.char_count,
            char_count_no_spaces=tab.char_count_no_spaces, last_edited_at=now,
        ))
    created = EssayTab.objects.bulk_create(copies)
    for original, copy in zip(top, created):
        new_parent[original.pk] = copy.pk
    children = [
        EssayTab(
            essay_id=essay.pk, parent_id=new_parent[tab.parent_id], title=tab.title, position=tab.position,
            doc=tab.doc, content=tab.content, word_count=tab.word_count, char_count=tab.char_count,
            char_count_no_spaces=tab.char_count_no_spaces, last_edited_at=now,
        )
        for tab in originals if tab.parent_id in new_parent
    ]
    return [*created, *EssayTab.objects.bulk_create(children)]


class EssayFolderViewSet(EssayLabViewMixin, viewsets.GenericViewSet):
    serializer_class = FolderSerializer
    student_context_actions = {'create', 'partial_update', 'order'}

    def get_queryset(self):
        return EssayFolder.objects.filter(student__user=self.request.user)

    def _folders_response(self):
        folders = self.get_queryset().annotate(
            essay_count=Count('essays', filter=Q(essays__trashed_at__isnull=True)),
        ).order_by('position', 'id')
        return Response(FolderSerializer(folders, many=True).data)

    def _get_folder(self, pk, lock=False):
        queryset = self.get_queryset()
        if lock:
            queryset = queryset.select_for_update(of=('self',))
        folder = queryset.filter(pk=pk).first()
        if folder is None:
            raise exceptions.NotFound('Folder not found.')
        return folder

    def _next_position(self, student_id, parent_id):
        current = EssayFolder.objects.filter(student_id=student_id, parent_id=parent_id).aggregate(
            last=Coalesce(Max('position'), Value(-1)),
        )['last']
        return current + 1

    @staticmethod
    def _check_parent(parent, folder=None):
        if parent is None:
            return
        if parent.parent_id is not None:
            raise EssayLabError('Folders can only be nested one level deep.', 'nesting_limit')
        if folder is not None:
            if parent.pk == folder.pk:
                raise EssayLabError('A folder cannot be inside itself.', 'nesting_limit')
            if folder.children.exists():
                raise EssayLabError('A folder with subfolders cannot be nested.', 'nesting_limit')

    def list(self, request):
        return self._folders_response()

    def create(self, request):
        serializer = FolderWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        student_id = self.student_id()
        parent = serializer.validated_data.get('parent')
        self._check_parent(parent)
        if EssayFolder.objects.filter(student_id=student_id).count() >= MAX_FOLDERS:
            raise EssayLabError(f'You can have up to {MAX_FOLDERS} folders.', 'too_many_folders')
        folder = EssayFolder.objects.create(
            student_id=student_id,
            name=serializer.validated_data['name'],
            parent=parent,
            position=self._next_position(student_id, parent.pk if parent else None),
        )
        return Response(FolderSerializer(folder).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        folder = self._get_folder(pk)
        serializer = FolderWriteSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        update_fields = ['updated_at']
        if 'name' in values:
            folder.name = values['name']
            update_fields.append('name')
        new_parent_id = values['parent'].pk if values.get('parent') else None
        if 'parent' in values and new_parent_id != folder.parent_id:
            parent = values['parent']
            self._check_parent(parent, folder)
            folder.parent = parent
            folder.position = self._next_position(folder.student_id, new_parent_id)
            update_fields += ['parent', 'position']
        folder.save(update_fields=update_fields)
        return Response(FolderSerializer(folder).data)

    def update(self, request, pk=None):
        raise exceptions.MethodNotAllowed('PUT')

    def destroy(self, request, pk=None):
        with transaction.atomic():
            folder = self._get_folder(pk, lock=True)
            # Subfolders move up to the top level, after the existing top-level folders.
            children = list(folder.children.order_by('position', 'id'))
            if children:
                start = self._next_position(folder.student_id, None)
                for offset, child in enumerate(children):
                    child.parent = None
                    child.position = start + offset
                EssayFolder.objects.bulk_update(children, ['parent', 'position'])
            # Essays fall back to "no folder" through the SET_NULL foreign key.
            folder.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['put'])
    def order(self, request):
        serializer = FolderOrderSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data['parent']
        ids = serializer.validated_data['ids']
        with transaction.atomic():
            siblings = {
                folder.pk: folder
                for folder in self.get_queryset().select_for_update(of=('self',)).filter(parent=parent)
            }
            if len(ids) != len(set(ids)) or set(ids) != set(siblings):
                raise EssayLabError('Send every folder of this level exactly once.', 'order_mismatch')
            for position, folder_id in enumerate(ids):
                siblings[folder_id].position = position
            EssayFolder.objects.bulk_update(siblings.values(), ['position'])
        return self._folders_response()
