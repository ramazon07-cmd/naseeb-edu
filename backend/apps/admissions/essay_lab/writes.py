"""Writing a tab's text and its history (shared by autosave, restores and feedback)."""

from django.db.models import Case, IntegerField, Value, When

from ..models import EssayCheckpoint

CHECKPOINT_CAP = 200
TEXT_FIELDS = ['doc', 'content', 'word_count', 'char_count', 'char_count_no_spaces']


def prune_checkpoints(essay_id):
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


def make_checkpoint(essay, tab, reason, label='', *, author=None, kind=EssayCheckpoint.Kind.EDIT, detail=None):
    """Snapshot the tab's current text, saying who made it and why."""
    from .doc import tab_doc

    checkpoint = EssayCheckpoint.objects.create(
        essay_id=essay.pk,
        tab=tab,
        doc=tab_doc(tab),
        content=tab.content,
        word_count=tab.word_count,
        reason=reason,
        label=label,
        author=author,
        kind=kind,
        detail=detail or {},
    )
    prune_checkpoints(essay.pk)
    return checkpoint


def set_text(tab, doc, stats):
    tab.doc = doc
    tab.content = stats.content
    tab.word_count = stats.word_count
    tab.char_count = stats.char_count
    tab.char_count_no_spaces = stats.char_count_no_spaces
