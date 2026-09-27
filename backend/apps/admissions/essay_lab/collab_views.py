"""Comments and suggestions: the student's actions and the staff review API.

Students act through `/api/essay-lab/essays/<id>/…` (StudentCollabMixin on the
Essay Lab viewset). Staff use `/api/essay-lab/review/essays/<id>/…`, where every
request goes through `resolve_access`: only the assigned counselor of the
student, in the same school, while the essay is shared; a platform admin may
read. Anyone else gets 404, exactly as if the essay did not exist.

Every change to the doc happens here under the essay and tab row locks, bumps
the tab's save_seq (so the student's editor merges it) and `Essay.collab_seq`
(so a poll notices). Notifications never quote the essay.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import F, Prefetch
from django.utils import timezone
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.users.audit import audit_product_action
from apps.users.models import User
from ..models import (
    Essay, EssayCheckpoint, EssayComment, EssayCommentThread, EssaySuggestion, EssayTab, EssayTabEdit, Notification,
)
from . import access
from .collab import MAX_QUOTE, find_block, insert_text, mark_range, resolve_suggestions
from .doc import DocError, doc_stats, ensure_bids, tab_doc, validate_doc
from .serializers import (
    ChangesQuerySerializer, CommentBodySerializer, DecideSerializer, SuggestionCreateSerializer, TabMetaSerializer,
    ThreadCreateSerializer, person_name,
)
from .tabs import refresh_essay_text, tree_order
from .writes import TEXT_FIELDS, make_checkpoint, set_text

# Someone else counts as "here" for this long after their last request.
PRESENCE_WINDOW = timedelta(seconds=45)
# A staff reader's presence is written at most this often.
PRESENCE_WRITE_EVERY = timedelta(seconds=15)
CHANGE_KINDS = {
    'comment': EssayCheckpoint.Kind.COMMENT,
    'suggest': EssayCheckpoint.Kind.SUGGEST,
    'decision': EssayCheckpoint.Kind.DECISION,
}


class CollabError(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'error'

    def __init__(self, detail, code, status_code=None):
        if status_code:
            self.status_code = status_code
        super().__init__(detail, code)


def _doc_error(exc):
    return CollabError(exc.detail, exc.code, exc.status)


# ----------------------------------------------------------------------- reading


def others_active(essay_staff_seen_at, now=None):
    now = now or timezone.now()
    return bool(essay_staff_seen_at and essay_staff_seen_at >= now - PRESENCE_WINDOW)


def _thread_data(thread, viewer_id):
    return {
        'id': thread.pk,
        'tab': thread.tab_id,
        'status': thread.status,
        'quote': thread.quote,
        'created_at': thread.created_at,
        'author_name': person_name(thread.author),
        'by_me': thread.author_id == viewer_id,
        'resolved_by_name': person_name(thread.resolved_by),
        'resolved_at': thread.resolved_at,
        'comments': [
            {'id': comment.pk, 'body': comment.body, 'created_at': comment.created_at,
             'author_name': person_name(comment.author), 'by_me': comment.author_id == viewer_id}
            for comment in thread.comments.all()
        ],
    }


def _suggestion_data(suggestion, viewer_id):
    return {
        'id': suggestion.pk,
        'tab': suggestion.tab_id,
        'status': suggestion.status,
        'delete_text': suggestion.delete_text,
        'insert_text': suggestion.insert_text,
        'created_at': suggestion.created_at,
        'author_name': person_name(suggestion.author),
        'by_me': suggestion.author_id == viewer_id,
    }


def feedback_for_tab(tab_id, viewer_id):
    """Every thread (with its comments) and every pending suggestion of one tab: three queries."""
    threads = (
        EssayCommentThread.objects.filter(tab_id=tab_id)
        .select_related('author', 'resolved_by')
        .prefetch_related(Prefetch('comments', queryset=EssayComment.objects.select_related('author')))
    )
    suggestions = EssaySuggestion.objects.filter(tab_id=tab_id, status=EssaySuggestion.Status.PENDING).select_related('author')
    return {
        'threads': [_thread_data(thread, viewer_id) for thread in threads],
        'suggestions': [_suggestion_data(suggestion, viewer_id) for suggestion in suggestions],
    }


def make_etag(save_seq, collab_seq, active):
    return f'"{save_seq}.{collab_seq}.{int(active)}"'


def etag_matches(request, etag):
    header = request.headers.get('If-None-Match', '')
    return etag in [part.strip().removeprefix('W/') for part in header.split(',') if part.strip()]


def changes_response(request, essay_id, tab_id, since, row, *, active):
    """304 when nothing changed since the client's ETag; otherwise the tab's feedback (and doc when newer)."""
    etag = make_etag(row['save_seq'], row['collab_seq'], active)
    headers = {'ETag': etag, 'Cache-Control': 'private, no-cache'}
    if etag_matches(request, etag):
        return Response(status=status.HTTP_304_NOT_MODIFIED, headers=headers)
    data = {
        'tab': tab_id, 'save_seq': row['save_seq'], 'collab_seq': row['collab_seq'], 'others_active': active,
        **feedback_for_tab(tab_id, request.user.pk),
    }
    if since != row['save_seq']:
        tab = EssayTab.objects.filter(pk=tab_id, essay_id=essay_id).only('id', 'doc', 'content', 'save_seq').first()
        if tab is None:
            raise exceptions.NotFound('Tab not found.')
        data['save_seq'] = tab.save_seq
        data['doc'] = ensure_bids(tab_doc(tab))
    return Response(data, headers=headers)


# ----------------------------------------------------------------------- writing


def lock_tab(essay_id, tab_id):
    """The tab, locked; the caller already holds the essay row lock (every writer takes them in this order)."""
    tab = EssayTab.objects.select_for_update().filter(pk=tab_id, essay_id=essay_id).first()
    if tab is None:
        raise exceptions.NotFound('Tab not found.')
    return tab


def write_doc(essay, tab, doc, *, actor, owner_id, kind, detail):
    """Store a doc changed by feedback or decisions, with its history row and version."""
    try:
        doc = validate_doc(doc)
    except DocError as exc:
        raise _doc_error(exc)
    stats = doc_stats(doc)
    text_changed = stats.content != tab.content
    set_text(tab, doc, stats)
    tab.save_seq += 1
    # Null stands for the owner; anyone else is named so the owner's next save starts a new run.
    tab.last_editor_id = None if actor.pk == owner_id else actor.pk
    tab.save(update_fields=[*TEXT_FIELDS, 'save_seq', 'last_editor', 'updated_at'])
    if text_changed:
        refresh_essay_text(essay)
    EssayTabEdit.objects.create(essay_id=essay.pk, tab=tab, author=actor, kind=kind, save_seq=tab.save_seq,
                                detail=detail)
    make_checkpoint(essay, tab, EssayCheckpoint.Reason.AUTO, author=actor, kind=CHANGE_KINDS[kind], detail=detail)


def bump_collab(essay_id):
    Essay.objects.filter(pk=essay_id).update(collab_seq=F('collab_seq') + 1)


def notify(essay, *, title, message, recipient_id=None):
    """A notice about this essay: to the student (no recipient) or to one staff member. Never quotes it."""
    Notification.objects.create(
        student_id=essay.student_id, recipient_id=recipient_id, title=title, message=message,
        kind=Notification.Kind.ESSAY, target_id=essay.pk,
    )


def _plural(count, one, many):
    return f'{count} {one if count == 1 else many}'


def _thread_for(essay_id, thread_id, *, lock=False):
    queryset = EssayCommentThread.objects.filter(pk=thread_id, essay_id=essay_id)
    if lock:
        queryset = queryset.select_for_update()
    thread = queryset.first()
    if thread is None:
        raise exceptions.NotFound('Comment not found.')
    return thread


def add_reply(essay, thread_id, user, body):
    with transaction.atomic():
        thread = _thread_for(essay.pk, thread_id, lock=True)
        comment = EssayComment.objects.create(thread=thread, author=user, body=body)
        EssayCommentThread.objects.filter(pk=thread.pk).update(updated_at=timezone.now())
        bump_collab(essay.pk)
    return thread, comment


def set_thread_status(essay, thread_id, user, resolved):
    with transaction.atomic():
        thread = _thread_for(essay.pk, thread_id, lock=True)
        wanted = EssayCommentThread.Status.RESOLVED if resolved else EssayCommentThread.Status.OPEN
        changed = thread.status != wanted
        if changed:
            thread.status = wanted
            thread.resolved_by = user if resolved else None
            thread.resolved_at = timezone.now() if resolved else None
            thread.save(update_fields=['status', 'resolved_by', 'resolved_at', 'updated_at'])
            bump_collab(essay.pk)
    return thread, changed


def thread_response(thread, viewer_id, status_code=status.HTTP_200_OK):
    thread = (
        EssayCommentThread.objects.select_related('author', 'resolved_by')
        .prefetch_related(Prefetch('comments', queryset=EssayComment.objects.select_related('author')))
        .get(pk=thread.pk)
    )
    return Response(_thread_data(thread, viewer_id), status=status_code)


# ------------------------------------------------------------------ the student


class StudentCollabMixin:
    """Actions on the student's own essay (the Essay Lab viewset provides get_essay/resolve_tab)."""

    @action(detail=True, methods=['get'])
    def changes(self, request, pk=None):
        query = ChangesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        tab_id = query.validated_data['tab']
        # One query answers a 304: the tab, its essay's counters and the owner check.
        row = (
            EssayTab.objects.filter(pk=tab_id, essay_id=pk, essay__student__user=request.user)
            .values('save_seq', collab_seq=F('essay__collab_seq'), seen=F('essay__staff_seen_at')).first()
        )
        if row is None:
            raise exceptions.NotFound('Tab not found.')
        return changes_response(request, int(pk), tab_id, query.validated_data.get('since'), row,
                                active=others_active(row['seen']))

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/reply')
    def thread_reply(self, request, pk=None, tid=None):
        serializer = CommentBodySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        essay = self.get_essay(pk, defer=('content',))
        thread, _comment = add_reply(essay, int(tid), request.user, serializer.validated_data['body'])
        self._tell_counselors(essay, [thread.author_id], 'New reply to your comment',
                              f'{person_name(request.user)} replied to your comment on an essay.')
        return thread_response(thread, request.user.pk, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/resolve')
    def thread_resolve(self, request, pk=None, tid=None):
        essay = self.get_essay(pk, defer=('content',))
        thread, changed = set_thread_status(essay, int(tid), request.user, True)
        if changed:
            self._tell_counselors(essay, [thread.author_id], 'Comment resolved',
                                  f'{person_name(request.user)} resolved your comment on an essay.')
        return thread_response(thread, request.user.pk)

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/reopen')
    def thread_reopen(self, request, pk=None, tid=None):
        essay = self.get_essay(pk, defer=('content',))
        thread, _changed = set_thread_status(essay, int(tid), request.user, False)
        return thread_response(thread, request.user.pk)

    @action(detail=True, methods=['post'], url_path='suggestions/decide')
    def suggestions_decide(self, request, pk=None):
        """Accept or reject suggestions: all of them are applied to the doc in one transaction, or none."""
        serializer = DecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decisions = {item['id']: item['accept'] for item in serializer.validated_data['decisions']}
        with transaction.atomic():
            essay = self.get_essay(pk, lock=True, defer=('content',))
            tab = self.resolve_tab(essay, serializer.validated_data['tab'], lock=True)
            suggestions = list(
                EssaySuggestion.objects.select_for_update().filter(pk__in=decisions, essay_id=essay.pk, tab_id=tab.pk)
            )
            if len(suggestions) != len(decisions):
                raise exceptions.NotFound('Suggestion not found.')
            if any(item.status != EssaySuggestion.Status.PENDING for item in suggestions):
                raise CollabError('Some of these suggestions were already decided.', 'already_decided', 409)
            doc = resolve_suggestions(ensure_bids(tab_doc(tab)), decisions)
            now = timezone.now()
            for item in suggestions:
                item.status = EssaySuggestion.Status.ACCEPTED if decisions[item.pk] else EssaySuggestion.Status.REJECTED
                item.decided_by = request.user
                item.decided_at = now
            EssaySuggestion.objects.bulk_update(suggestions, ['status', 'decided_by', 'decided_at'])
            accepted = sum(decisions.values())
            detail = {'accepted': accepted, 'rejected': len(decisions) - accepted}
            write_doc(essay, tab, doc, actor=request.user, owner_id=request.user.pk, kind='decision', detail=detail)
            bump_collab(essay.pk)
            by_author = {}
            for item in suggestions:
                if item.author_id:
                    counts = by_author.setdefault(item.author_id, [0, 0])
                    counts[0 if decisions[item.pk] else 1] += 1
            name = person_name(request.user)
            for author_id, (yes, no) in by_author.items():
                parts = [f'accepted {_plural(yes, "suggestion", "suggestions")}' if yes else '',
                         f'rejected {_plural(no, "suggestion", "suggestions")}' if no else '']
                self._tell_counselors(essay, [author_id], 'Suggestions reviewed',
                                      f'{name} {" and ".join(part for part in parts if part)} on an essay.')
        return Response({
            'tab': tab.pk, 'save_seq': tab.save_seq, 'doc': ensure_bids(tab_doc(tab)),
            'word_count': tab.word_count, 'char_count': tab.char_count,
            'char_count_no_spaces': tab.char_count_no_spaces, 'document_word_count': essay.word_count,
            'decided': [{'id': item.pk, 'status': item.status} for item in suggestions],
        })

    def _tell_counselors(self, essay, author_ids, title, message):
        """Tell the staff authors of the feedback (never the student themself).

        Only those who can still open the essay: after an unshare or a change of
        counselor, the essay's activity is none of their business.
        """
        wanted = {author_id for author_id in author_ids if author_id and author_id != self.request.user.pk}
        if not wanted:
            return
        for author in User.objects.filter(pk__in=wanted):
            if access.VIEW in access.resolve_access(author, essay):
                notify(essay, title=title, message=message, recipient_id=author.pk)


# -------------------------------------------------------------------- the staff


class ReviewEssayViewSet(viewsets.GenericViewSet):
    """Staff side of shared essays. No counselor screen uses it yet; the student's editor shows its results."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    lookup_value_regex = '[0-9]+'

    def essay_with_access(self, pk, need, *, lock=False):
        queryset = Essay.objects.select_related('student__user', 'student__school').filter(pk=pk)
        if lock:
            queryset = queryset.select_for_update(of=('self',))
        essay = queryset.order_by().first()
        caps = access.resolve_access(self.request.user, essay) if essay is not None else access.NONE
        if access.VIEW not in caps or self.request.user.role == User.Role.STUDENT:
            # Missing, private, not theirs: all look the same.
            raise exceptions.NotFound('Essay not found.')
        if need not in caps:
            raise exceptions.PermissionDenied('Your access to this essay does not allow that.')
        # Any staff request means someone is in the essay: the student's editor polls faster.
        self.seen(essay)
        return essay, caps

    def tab_of(self, essay, tab_id):
        tab = EssayTab.objects.filter(pk=tab_id, essay_id=essay.pk).only('id', 'essay', 'save_seq', 'last_edited_at').first()
        if tab is None:
            raise exceptions.NotFound('Tab not found.')
        return tab

    def seen(self, essay):
        now = timezone.now()
        if essay.staff_seen_at is None or essay.staff_seen_at < now - PRESENCE_WRITE_EVERY:
            Essay.objects.filter(pk=essay.pk).update(staff_seen_at=now)
            essay.staff_seen_at = now

    def retrieve(self, request, pk=None):
        essay, caps = self.essay_with_access(pk, access.VIEW)
        metas = tree_order(list(EssayTab.objects.filter(essay_id=essay.pk).only(
            'id', 'essay', 'parent', 'title', 'position', 'word_count', 'char_count', 'char_count_no_spaces',
            'save_seq', 'last_edited_at')))
        if not metas:
            raise exceptions.NotFound('Tab not found.')
        wanted = request.query_params.get('tab')
        active = next((tab for tab in metas if wanted and str(tab.pk) == wanted), metas[0])
        tab = EssayTab.objects.get(pk=active.pk)
        if request.user.is_product_admin:
            audit_product_action(actor=request.user, action='essay.review_read', target=essay.student,
                                 metadata={'essay': essay.pk})
        return Response({
            'id': essay.pk, 'title': essay.title, 'prompt': essay.prompt, 'essay_type': essay.essay_type,
            'counselor_access': essay.counselor_access, 'capabilities': sorted(caps),
            'student_name': person_name(essay.student.user),
            'tabs': TabMetaSerializer(metas, many=True).data,
            'tab': {'id': tab.pk, 'title': tab.title, 'save_seq': tab.save_seq, 'doc': ensure_bids(tab_doc(tab))},
            **feedback_for_tab(tab.pk, request.user.pk),
        })

    @action(detail=True, methods=['get'])
    def changes(self, request, pk=None):
        query = ChangesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        essay, _caps = self.essay_with_access(pk, access.VIEW)
        tab = self.tab_of(essay, query.validated_data['tab'])
        # The student counts as present while their saves keep arriving.
        row = {'save_seq': tab.save_seq, 'collab_seq': essay.collab_seq}
        return changes_response(request, essay.pk, tab.pk, query.validated_data.get('since'), row,
                                active=others_active(tab.last_edited_at))

    @action(detail=True, methods=['post'])
    def threads(self, request, pk=None):
        serializer = ThreadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            essay, _caps = self.essay_with_access(pk, access.COMMENT, lock=True)
            tab = lock_tab(essay.pk, values['tab'])
            doc = ensure_bids(tab_doc(tab))
            index = find_block(doc, values['bid'])
            if index is None:
                raise CollabError('That paragraph is not in the essay any more.', 'invalid_range', 409)
            thread = EssayCommentThread.objects.create(essay=essay, tab=tab, author=request.user)
            try:
                block, quote = mark_range(doc['content'][index], values['start'], values['end'],
                                          {'type': 'comment', 'attrs': {'id': thread.pk}})
            except DocError as exc:
                raise _doc_error(exc)
            thread.quote = quote.strip()[:MAX_QUOTE]
            thread.save(update_fields=['quote'])
            EssayComment.objects.create(thread=thread, author=request.user, body=values['body'])
            content = list(doc['content'])
            content[index] = block
            write_doc(essay, tab, {**doc, 'content': content}, actor=request.user, owner_id=essay.student.user_id,
                      kind='comment', detail={'comments': 1})
            bump_collab(essay.pk)
            notify(essay, title='New feedback on your essay',
                   message=f'{person_name(request.user)} left a comment on your essay.')
        return thread_response(thread, request.user.pk, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/reply')
    def thread_reply(self, request, pk=None, tid=None):
        serializer = CommentBodySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        essay, _caps = self.essay_with_access(pk, access.COMMENT)
        thread, _comment = add_reply(essay, int(tid), request.user, serializer.validated_data['body'])
        notify(essay, title='New feedback on your essay',
               message=f'{person_name(request.user)} replied to a comment on your essay.')
        return thread_response(thread, request.user.pk, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/resolve')
    def thread_resolve(self, request, pk=None, tid=None):
        essay, _caps = self.essay_with_access(pk, access.COMMENT)
        thread, _changed = set_thread_status(essay, int(tid), request.user, True)
        return thread_response(thread, request.user.pk)

    @action(detail=True, methods=['post'], url_path=r'threads/(?P<tid>[0-9]+)/reopen')
    def thread_reopen(self, request, pk=None, tid=None):
        essay, _caps = self.essay_with_access(pk, access.COMMENT)
        thread, _changed = set_thread_status(essay, int(tid), request.user, False)
        return thread_response(thread, request.user.pk)

    @action(detail=True, methods=['post'])
    def suggestions(self, request, pk=None):
        """Several suggested edits at once; offsets refer to the text as the reviewer saw it."""
        serializer = SuggestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            essay, _caps = self.essay_with_access(pk, access.SUGGEST, lock=True)
            tab = lock_tab(essay.pk, values['tab'])
            doc = ensure_bids(tab_doc(tab))
            content = list(doc['content'])
            items = values['items']
            # Later ranges first, so earlier offsets still point at the same text.
            by_block = {}
            for item in items:
                by_block.setdefault(item['bid'], []).append(item)
            created = []
            for bid, block_items in by_block.items():
                index = find_block(doc, bid)
                if index is None:
                    raise CollabError('That paragraph is not in the essay any more.', 'invalid_range', 409)
                block_items.sort(key=lambda item: (item['start'], item['end']))
                for before, after in zip(block_items, block_items[1:]):
                    if after['start'] < before['end'] or (after['start'] == before['end'] and before['text']):
                        raise CollabError('Suggestions cannot overlap.', 'invalid_range')
                block = content[index]
                for item in reversed(block_items):
                    suggestion = EssaySuggestion.objects.create(essay=essay, tab=tab, author=request.user,
                                                                insert_text=item['text'])
                    try:
                        if item['end'] > item['start']:
                            block, removed = mark_range(block, item['start'], item['end'],
                                                        {'type': 'suggestDelete', 'attrs': {'id': suggestion.pk}})
                            suggestion.delete_text = removed[:2000]
                        if item['text']:
                            block = insert_text(block, item['end'], item['text'],
                                                {'type': 'suggestInsert', 'attrs': {'id': suggestion.pk}})
                    except DocError as exc:
                        raise _doc_error(exc)
                    suggestion.save(update_fields=['delete_text'])
                    created.append(suggestion)
                content[index] = block
            count = len(created)
            write_doc(essay, tab, {**doc, 'content': content}, actor=request.user, owner_id=essay.student.user_id,
                      kind='suggest', detail={'suggestions': count})
            bump_collab(essay.pk)
            notify(essay, title='New feedback on your essay',
                   message=f'{person_name(request.user)} suggested {_plural(count, "edit", "edits")} to your essay.')
        created.sort(key=lambda item: item.pk)
        return Response({'suggestions': [_suggestion_data(item, request.user.pk) for item in created],
                         'save_seq': tab.save_seq}, status=status.HTTP_201_CREATED)
