"""Comments and suggestions inside an Essay Lab doc.

Feedback lives in the doc as marks, so it follows the words as the student
edits: `comment{id}` over the commented words, `suggestInsert{id}` on proposed
new text and `suggestDelete{id}` on text proposed for removal (ids are
EssayCommentThread / EssaySuggestion ids). Suggested insertions are left out of
the essay's plain text and counts until the student accepts them (doc.py).

Staff address text by a top-level block id (`bid`) and offsets inside it.
Offsets count UTF-16 code units, as the browser editor does: the block's text
blocks follow one another with one separator unit between them, and a hard line
break counts as one unit.

The docs produced here are what the editor itself would produce when loading
them (ProseMirror joins neighbouring text with equal marks and orders marks by
type), so a student's editor never sees a difference it did not make.
"""

import copy

from .doc import COLLAB_MARKS, TEXT_BLOCKS, DocError, block_id

MAX_BODY = 2000
MAX_QUOTE = 300
MAX_SUGGESTED_TEXT = 2000
# Collaboration marks come after every formatting mark, in this order (the
# editor registers them last with falling priority).
MARK_RANK = {name: index + 1 for index, name in enumerate(COLLAB_MARKS)}


def _invalid(detail):
    return DocError('invalid_range', detail)


def _u16(text):
    return len(text.encode('utf-16-le')) // 2


def _u16_slice(text, start, end=None):
    data = text.encode('utf-16-le')
    piece = data[start * 2:] if end is None else data[start * 2:end * 2]
    try:
        return piece.decode('utf-16-le')
    except UnicodeDecodeError:
        raise _invalid('A range cannot split a character.')


def _leaves(node, out):
    """Every text block inside `node`, in reading order (the dicts themselves)."""
    if node.get('type') in TEXT_BLOCKS:
        out.append(node)
        return out
    for child in node.get('content') or []:
        if isinstance(child, dict):
            _leaves(child, out)
    return out


def _leaf_length(leaf):
    return sum(_u16(child.get('text', '')) if child.get('type') == 'text' else 1 for child in leaf.get('content') or [])


def _spans(block):
    """[(leaf, start, end)] with global offsets; one separator unit between leaves."""
    spans = []
    position = 0
    for index, leaf in enumerate(_leaves(block, [])):
        if index:
            position += 1
        length = _leaf_length(leaf)
        spans.append((leaf, position, position + length))
        position += length
    return spans


def block_length(block):
    spans = _spans(block)
    return spans[-1][2] if spans else 0


def _rank(mark):
    return MARK_RANK.get(mark.get('type'), 0)


def _key(mark):
    return (mark['type'], mark['attrs']['id']) if mark.get('type') == 'comment' else mark.get('type')


def _with_mark(marks, mark):
    kept = [item for item in marks or () if _key(item) != _key(mark)]
    # A stable sort keeps the formatting marks' order and puts the new mark last in its group.
    return sorted([*kept, mark], key=_rank)


def _normalize_inline(content):
    """Join neighbouring text nodes with equal marks and drop empty ones (as ProseMirror does)."""
    joined = []
    for node in content:
        if node.get('type') == 'text':
            if not node.get('text'):
                continue
            previous = joined[-1] if joined else None
            if previous is not None and previous.get('type') == 'text' and previous.get('marks') == node.get('marks'):
                joined[-1] = {**previous, 'text': previous['text'] + node['text']}
                continue
        joined.append(node)
    return joined


def _set_content(leaf, content):
    content = _normalize_inline(content)
    if content:
        leaf['content'] = content
    else:
        leaf.pop('content', None)


def _text_node(text, marks):
    return {'type': 'text', 'text': text, 'marks': marks} if marks else {'type': 'text', 'text': text}


def _map_range(leaf, start, end, change, collected):
    """Apply `change(node) -> node | None` to the text inside [start, end) of one leaf."""
    content = []
    position = 0
    for node in leaf.get('content') or []:
        if node.get('type') != 'text':
            content.append(node)
            position += 1
            continue
        text = node['text']
        length = _u16(text)
        node_start, node_end = position, position + length
        position = node_end
        if node_end <= start or node_start >= end:
            content.append(node)
            continue
        cut_from = max(start, node_start) - node_start
        cut_to = min(end, node_end) - node_start
        before, middle, after = _u16_slice(text, 0, cut_from), _u16_slice(text, cut_from, cut_to), _u16_slice(text, cut_to)
        if before:
            content.append({**node, 'text': before})
        if not any(mark.get('type') == 'suggestInsert' for mark in node.get('marks') or ()):
            collected.append(middle)
        changed = change({**node, 'text': middle})
        if changed is not None:
            content.append(changed)
        if after:
            content.append({**node, 'text': after})
    _set_content(leaf, content)


def _check_range(block, start, end, *, allow_empty):
    total = block_length(block)
    if not (isinstance(start, int) and isinstance(end, int)) or isinstance(start, bool) or isinstance(end, bool):
        raise _invalid('A range needs whole-number offsets.')
    if not 0 <= start <= end <= total or (start == end and not allow_empty):
        raise _invalid('That text is not in the paragraph any more.')


def mark_range(block, start, end, mark):
    """A copy of `block` with `mark` over [start, end), and the plain text it covers."""
    _check_range(block, start, end, allow_empty=False)
    block = copy.deepcopy(block)
    collected = []
    for leaf, leaf_start, leaf_end in _spans(block):
        if leaf_end <= start or leaf_start >= end:
            continue
        piece_start, piece_end = max(start, leaf_start) - leaf_start, min(end, leaf_end) - leaf_start
        if collected:
            collected.append('\n')
        _map_range(leaf, piece_start, piece_end,
                    lambda node: {**node, 'marks': _with_mark(node.get('marks'), mark)}, collected)
    return block, ''.join(collected)


def insert_text(block, at, text, mark):
    """A copy of `block` with `text` (carrying `mark` and the formatting around it) inserted at `at`."""
    _check_range(block, at, at, allow_empty=True)
    block = copy.deepcopy(block)
    spans = _spans(block)
    if not spans:
        raise _invalid('Suggestions go into text paragraphs.')
    # The leaf holding `at`; an offset on a separator belongs to the leaf before it.
    leaf, leaf_start, _leaf_end = next((span for span in spans if span[1] <= at <= span[2]), spans[-1])
    local = at - leaf_start
    content = []
    position = 0
    inserted = False
    neighbour_marks = None
    for node in leaf.get('content') or []:
        length = _u16(node['text']) if node.get('type') == 'text' else 1
        if not inserted and node.get('type') == 'text' and position <= local <= position + length and local > position:
            cut = local - position
            content.append({**node, 'text': _u16_slice(node['text'], 0, cut)})
            neighbour_marks = node.get('marks')
            content.append(('insert',))
            rest = _u16_slice(node['text'], cut)
            if rest:
                content.append({**node, 'text': rest})
            inserted = True
        elif not inserted and local == position:
            if neighbour_marks is None and node.get('type') == 'text':
                neighbour_marks = node.get('marks')
            content.append(('insert',))
            content.append(node)
            inserted = True
        else:
            content.append(node)
        position += length
    if not inserted:
        if content and content[-1].get('type') == 'text':
            neighbour_marks = content[-1].get('marks')
        content.append(('insert',))
    formatting = [item for item in neighbour_marks or () if item.get('type') not in COLLAB_MARKS]
    new_node = _text_node(text, _with_mark(formatting, mark))
    _set_content(leaf, [new_node if node == ('insert',) else node for node in content])
    return block


def resolve_suggestions(doc, decisions):
    """A copy of `doc` with the suggestions in `decisions` ({id: accepted?}) applied.

    Accepting an insertion keeps its text, rejecting removes it; accepting a
    deletion removes the text, rejecting keeps it. Every other mark stays.
    """
    doc = copy.deepcopy(doc)

    def visit(node):
        if node.get('type') in TEXT_BLOCKS:
            content = []
            for child in node.get('content') or []:
                if child.get('type') == 'text':
                    child = _decide(child, decisions)
                    if child is None:
                        continue
                content.append(child)
            _set_content(node, content)
            return
        for child in node.get('content') or []:
            if isinstance(child, dict):
                visit(child)

    visit(doc)
    return doc


def _decide(node, decisions):
    marks = []
    for mark in node.get('marks') or ():
        mark_id = (mark.get('attrs') or {}).get('id')
        if mark.get('type') in {'suggestInsert', 'suggestDelete'} and mark_id in decisions:
            accepted = decisions[mark_id]
            removes_text = accepted if mark['type'] == 'suggestDelete' else not accepted
            if removes_text:
                return None
            continue
        marks.append(mark)
    return _text_node(node['text'], marks)


def find_block(doc, bid):
    return next((index for index, block in enumerate(doc.get('content') or []) if block_id(block) == bid), None)


def mark_ids(doc, mark_type):
    """Ids of every `mark_type` mark in the doc."""
    found = set()

    def visit(node):
        for mark in node.get('marks') or ():
            if mark.get('type') == mark_type:
                found.add((mark.get('attrs') or {}).get('id'))
        for child in node.get('content') or []:
            if isinstance(child, dict):
                visit(child)

    visit(doc)
    return found
