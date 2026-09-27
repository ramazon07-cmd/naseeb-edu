"""Document tabs: ordering and the essay-level text derived from them.

An Essay is the document; its text lives in ordered EssayTab rows, one level
of sub-tabs deep. `Essay.content`, `word_count` and `preview` are derived from
the tabs in the same transaction as every tab write, so counselors, search and
the legacy API keep reading one plain text.
"""

from django.db.models import F

from ..models import Essay, EssayTab
from .doc import doc_from_text, doc_stats, make_preview

MAX_TABS = 100
MAX_TAB_TITLE = 100
FIRST_TAB_TITLE = 'Tab 1'
# Everything the tab rail and the counters need, never the doc.
META_FIELDS = (
    'id', 'essay_id', 'parent_id', 'title', 'position', 'word_count', 'char_count', 'char_count_no_spaces',
    'save_seq', 'last_edited_at',
)


def tree_order(tabs):
    """Tabs in reading order: each top-level tab followed by its sub-tabs."""
    key = lambda tab: (tab.position, tab.pk)  # noqa: E731
    children = {}
    top = []
    for tab in tabs:
        if tab.parent_id is None:
            top.append(tab)
        else:
            children.setdefault(tab.parent_id, []).append(tab)
    ordered = []
    for tab in sorted(top, key=key):
        ordered.append(tab)
        ordered.extend(sorted(children.get(tab.pk, ()), key=key))
    return ordered


def combined_text(tabs):
    """(content, word_count, preview) of the whole document from its ordered tabs.

    One tab: its text as is (so a plain essay reads exactly as before). Several:
    each tab's title above its text. The preview skips the titles.
    """
    if len(tabs) == 1:
        tab = tabs[0]
        return tab.content, tab.word_count, make_preview(tab.content)
    parts = []
    for tab in tabs:
        parts.append(f'{tab.title}\n\n{tab.content}' if tab.content else tab.title)
    body = '\n\n'.join(tab.content for tab in tabs if tab.content)
    return '\n\n'.join(parts), sum(tab.word_count for tab in tabs), make_preview(body)


def refresh_essay_text(essay, tabs=None, now=None, extra_fields=()):
    """Re-derive the essay's text columns from its tabs and save them.

    `tabs` may be passed when the caller already holds fresh copies (with
    `content`); otherwise they are read in one query. The caller holds the
    essay row lock.
    """
    if tabs is None:
        tabs = list(EssayTab.objects.filter(essay_id=essay.pk).only(
            'id', 'parent_id', 'position', 'title', 'content', 'word_count',
        ))
    content, word_count, preview = combined_text(tree_order(tabs))
    essay.content = content
    essay.word_count = word_count
    essay.preview = preview
    fields = ['content', 'word_count', 'preview', 'updated_at', *extra_fields]
    if now is not None:
        essay.last_edited_at = now
        fields.append('last_edited_at')
    essay.save(update_fields=fields)


def tab_from_text(essay, content, *, title=FIRST_TAB_TITLE, position=0, parent=None):
    """An unsaved tab holding plain text (legacy essays and plain-text writes)."""
    stats = doc_stats(doc_from_text(content))
    return EssayTab(
        essay=essay, parent=parent, title=title, position=position, doc=None, content=content or '',
        word_count=stats.word_count, char_count=stats.char_count, char_count_no_spaces=stats.char_count_no_spaces,
        last_edited_at=essay.last_edited_at,
    )


def ensure_first_tab(essay):
    """Give an essay created outside the Essay Lab (seed data, admin) its first tab.

    Locks the essay so two first opens can't both create one. Returns the tab.
    """
    locked = Essay.objects.select_for_update().only('id', 'content', 'last_edited_at').get(pk=essay.pk)
    existing = EssayTab.objects.filter(essay_id=essay.pk).order_by('parent_id', 'position', 'id').first()
    if existing is not None:
        return existing
    tab = tab_from_text(locked, locked.content)
    tab.save()
    return tab


def shift_after(essay_id, parent_id, position):
    """Make room right after `position` among siblings (one UPDATE)."""
    EssayTab.objects.filter(essay_id=essay_id, parent_id=parent_id, position__gt=position).update(
        position=F('position') + 1,
    )
