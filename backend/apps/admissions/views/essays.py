"""Admissions API views — essays."""
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from ..models import Essay, EssayRevision, EssayTab
from ..serializers import EssaySerializer
from ..essay_lab.doc import count_words, make_preview
from ..essay_lab.tabs import tab_from_text
from ..scoping import owns_essays_only, scope_essays, shared_essay_lookups
from .common import ScopedQuerysetMixin, StudentRecordListMixin


class EssayViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = EssaySerializer
    queryset = (
        Essay.objects.select_related('student__user', 'student__assigned_counselor', 'application__university')
        .prefetch_related(Prefetch(
            'revisions',
            queryset=EssayRevision.objects.select_related('created_by').defer('prompt', 'content', 'counselor_comment'),
        ))
    )
    search_fields = ('title',)
    choice_filters = {'status': ('status', Essay.Status.choices)}

    def get_queryset(self):
        return scope_essays(self.queryset, self.request.user).filter(trashed_at__isnull=True)

    def perform_create(self, serializer):
        content = serializer.validated_data.get('content', '')
        extra = {}
        if not owns_essays_only(self.request.user):
            # Staff wrote it for the student, so it starts out shared with them.
            extra = {'shared_with_counselor': True, 'shared_at': timezone.now()}
        with transaction.atomic():
            essay = serializer.save(word_count=count_words(content), preview=make_preview(content), **extra)
            # The text becomes the document's first tab in the Essay Lab.
            tab_from_text(essay, content).save()
            self._create_revision(essay)

    def _create_revision(self, essay):
        EssayRevision.objects.create(
            essay=essay,
            version=essay.version,
            prompt=essay.prompt,
            content=essay.content,
            status=essay.status,
            counselor_comment=essay.counselor_comment,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        tracked_fields = {'prompt', 'content', 'status', 'counselor_comment'}
        should_version = bool(tracked_fields.intersection(serializer.validated_data))
        with transaction.atomic():
            # Lock and reload the row so two concurrent edits can't both write the same
            # version and a full save can't overwrite a newer Essay Lab autosave.
            # The sharing check is repeated under the lock: an unshare that just committed wins.
            essay = (
                Essay.objects.select_for_update()
                .filter(pk=serializer.instance.pk, **shared_essay_lookups(self.request.user))
                .first()
            )
            if essay is None:
                raise NotFound()
            serializer.instance = essay
            extra = {}
            content = serializer.validated_data.get('content')
            if content is not None and content != essay.content:
                self._replace_text(essay, content)
                extra.update(word_count=count_words(content), preview=make_preview(content))
            if should_version:
                extra['version'] = essay.version + 1
            essay = serializer.save(**extra)
            if should_version:
                self._create_revision(essay)

    @staticmethod
    def _replace_text(essay, content):
        """A plain-text edit replaces the text of a one-tab document.

        The tab's rich doc no longer matches, so the Essay Lab rebuilds it from
        the text, and the bumped save_seq makes any in-flight autosave get a 409
        instead of overwriting. A document with several tabs can't be mapped
        back from one plain text, so it is only edited in the Essay Lab.
        """
        tabs = list(EssayTab.objects.select_for_update().filter(essay_id=essay.pk).defer('doc')[:2])
        if len(tabs) > 1:
            raise serializers.ValidationError(
                {'content': 'This document has several tabs. The student edits its text in the Essay Lab.'},
            )
        if not tabs:
            tab_from_text(essay, content).save()
            return
        tab = tabs[0]
        fresh = tab_from_text(essay, content)
        tab.doc = None
        tab.content = content
        tab.word_count = fresh.word_count
        tab.char_count = fresh.char_count
        tab.char_count_no_spaces = fresh.char_count_no_spaces
        tab.save_seq += 1
        tab.save(update_fields=['doc', 'content', 'word_count', 'char_count', 'char_count_no_spaces', 'save_seq',
                                'updated_at'])


