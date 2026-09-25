"""ProseMirror document validation and plain-text derivation for the Essay Lab.

The editor stores rich text as ProseMirror JSON in `EssayTab.doc`. Everything the
rest of the product reads (counselor views, word counts, AI checks) uses the
plain text derived here, so the rules must stay identical to the frontend's
`docText` helper. `fixtures/doc_text_cases.json` holds the shared cases.

Autosave can also send a delta: ops over the list of top-level blocks plus the
sha256 of the resulting document in canonical JSON. The canonical form and the
op format must match the frontend's `docDelta.js`; `fixtures/doc_delta_cases.json`
holds the shared cases.
"""

import hashlib
import json
import re
from typing import NamedTuple

MAX_DOC_BYTES = 256 * 1024
MAX_DEPTH = 12
PREVIEW_CHARS = 160

TEXT_BLOCKS = {'paragraph', 'heading', 'title', 'subtitle'}
BLOCK_NODES = TEXT_BLOCKS | {'bulletList', 'orderedList', 'listItem', 'blockquote', 'pageBreak'}
INLINE_NODES = {'text', 'hardBreak'}
ALLOWED_NODES = {'doc'} | BLOCK_NODES | INLINE_NODES
ALLOWED_MARKS = {'bold', 'italic', 'underline', 'strike', 'textStyle', 'highlight', 'link'}
BULLET_STYLES = {'bullet', 'dash'}
FLOW = TEXT_BLOCKS | {'bulletList', 'orderedList', 'blockquote'}
# Children each container may hold. Anything else is an invalid document.
# A page break only sits between top-level blocks.
ALLOWED_CHILDREN = {
    'doc': FLOW | {'pageBreak'},
    'blockquote': FLOW,
    'bulletList': {'listItem'},
    'orderedList': {'listItem'},
    'listItem': FLOW,
    'paragraph': INLINE_NODES,
    'heading': INLINE_NODES,
    'title': INLINE_NODES,
    'subtitle': INLINE_NODES,
}
HEADING_LEVELS = (1, 2, 3)
# Block formatting. The default of each (left, the page's line height, no
# indent) is stored as "no attribute", so there is one form per look.
TEXT_ALIGN = {'center', 'right', 'justify'}
LINE_HEIGHTS = {'1', '1.15', '1.5', '2'}
MAX_INDENT = 8
# Text formatting. Fonts come from this list only (the editor loads them).
FONT_FAMILIES = {
    'Arial', 'Times New Roman', 'Georgia', 'Courier New', 'Verdana',
    'Newsreader', 'Montserrat', 'Merriweather', 'Lora', 'Roboto',
}
FONT_SIZE_RANGE = (8, 96)
HEX_COLOR = re.compile(r'#[0-9a-fA-F]{6}')
MAX_HREF = 2048
# Spelled out (no IGNORECASE, no \\s) so the frontend's regex accepts exactly the same hrefs.
LINK_HREF = re.compile(
    '(?:[hH][tT][tT][pP][sS]?://|[mM][aA][iI][lL][tT][oO]:)'
    '[^\\x00-\\x20\\x7f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff<>"]+'
)
WORD_PATTERN = re.compile(r'\S+')
BLANK_LINE_PATTERN = re.compile(r'\n[ \t]*\n+')
WHITESPACE_PATTERN = re.compile(r'\s+')
# NUL is rejected by PostgreSQL text/jsonb; other C0 controls have no place in prose.
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class DocError(ValueError):
    def __init__(self, code, detail, status=400):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def _invalid(detail):
    return DocError('invalid_doc', detail)


def clean_text(value):
    return CONTROL_CHARS.sub('', str(value or ''))


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _one_of(value, allowed):
    """Set membership that never raises on unhashable JSON values (lists, objects)."""
    return isinstance(value, str) and value in allowed


def _color(value, what):
    if value is None:
        return None
    if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
        raise _invalid(f'{what} must be a #RRGGBB colour.')
    return value.lower()


def _mark_attrs(mark_type, attrs):
    """Allowed attributes of a mark, or None when the mark carries nothing (it is dropped)."""
    if attrs is not None and not isinstance(attrs, dict):
        raise _invalid('Mark attrs must be an object.')
    attrs = attrs or {}
    if mark_type == 'textStyle':
        cleaned = {}
        family = attrs.get('fontFamily')
        if family is not None:
            if not _one_of(family, FONT_FAMILIES):
                raise _invalid('That font is not available.')
            cleaned['fontFamily'] = family
        size = attrs.get('fontSize')
        if size is not None:
            if not _is_int(size) or not FONT_SIZE_RANGE[0] <= size <= FONT_SIZE_RANGE[1]:
                raise _invalid(f'Font size must be {FONT_SIZE_RANGE[0]} to {FONT_SIZE_RANGE[1]}.')
            cleaned['fontSize'] = size
        color = _color(attrs.get('color'), 'Text colour')
        if color:
            cleaned['color'] = color
        return cleaned or None
    if mark_type == 'highlight':
        color = _color(attrs.get('color'), 'Highlight colour')
        return {'color': color} if color else None
    if mark_type == 'link':
        href = attrs.get('href')
        if not isinstance(href, str) or len(href) > MAX_HREF or not LINK_HREF.fullmatch(href):
            raise _invalid('Links must be http, https or mailto addresses.')
        return {'href': href}
    return {}


def _clean_marks(marks):
    if marks is None:
        return None
    if not isinstance(marks, list) or len(marks) > len(ALLOWED_MARKS):
        raise _invalid('Text marks must be a short list.')
    cleaned = []
    seen = set()
    for mark in marks:
        if not isinstance(mark, dict) or not _one_of(mark.get('type'), ALLOWED_MARKS):
            raise _invalid('That text formatting is not allowed.')
        mark_type = mark['type']
        attrs = _mark_attrs(mark_type, mark.get('attrs'))
        if mark_type in seen or attrs is None:
            continue
        seen.add(mark_type)
        cleaned.append({'type': mark_type, 'attrs': attrs} if attrs else {'type': mark_type})
    return cleaned or None


def _block_format(attrs, cleaned):
    align = attrs.get('textAlign')
    if align is not None and align != 'left':
        if not _one_of(align, TEXT_ALIGN):
            raise _invalid('Unknown text alignment.')
        cleaned['textAlign'] = align
    line_height = attrs.get('lineHeight')
    if line_height is not None:
        if not _one_of(line_height, LINE_HEIGHTS):
            raise _invalid('Unknown line spacing.')
        cleaned['lineHeight'] = line_height
    indent = attrs.get('indent')
    if indent is not None:
        if not _is_int(indent) or not 0 <= indent <= MAX_INDENT:
            raise _invalid(f'Indent must be 0 to {MAX_INDENT}.')
        if indent:
            cleaned['indent'] = indent
    return cleaned


def _clean_attrs(node_type, attrs):
    """Keep only the attributes the editor schema defines; reject bad values."""
    if attrs is not None and not isinstance(attrs, dict):
        raise _invalid('Node attrs must be an object.')
    attrs = attrs or {}
    if node_type == 'heading':
        level = attrs.get('level')
        if level not in HEADING_LEVELS or isinstance(level, bool):
            raise _invalid('Headings must be level 1, 2 or 3.')
        return _block_format(attrs, {'level': level})
    if node_type in TEXT_BLOCKS:
        return _block_format(attrs, {}) or None
    if node_type == 'bulletList':
        style = attrs.get('style')
        if style is None:
            return None
        if not _one_of(style, BULLET_STYLES):
            raise _invalid('Unknown bullet list style.')
        return {'style': style}
    if node_type == 'orderedList':
        start = attrs.get('start', 1)
        if start is None:
            start = 1
        if not _is_int(start) or not 0 <= start <= 10000:
            raise _invalid('Ordered list start must be a small number.')
        return {'start': start} if start != 1 else None
    return None


def _clean_node(node, depth, allowed_types):
    if depth > MAX_DEPTH:
        raise _invalid(f'Documents cannot be nested deeper than {MAX_DEPTH} levels.')
    if not isinstance(node, dict):
        raise _invalid('Every node must be an object.')
    node_type = node.get('type')
    if not _one_of(node_type, ALLOWED_NODES):
        raise _invalid(f'Node type "{str(node_type)[:40]}" is not allowed.')
    if node_type not in allowed_types:
        raise _invalid(f'"{node_type}" cannot appear here.')

    if node_type == 'text':
        if not isinstance(node.get('text'), str):
            raise _invalid('Text nodes need a text string.')
        text = clean_text(node['text'])
        if not text:
            return None
        cleaned = {'type': 'text', 'text': text}
        marks = _clean_marks(node.get('marks'))
        if marks:
            cleaned['marks'] = marks
        return cleaned
    if node.get('marks'):
        raise _invalid('Only text nodes can carry marks.')
    if node_type in {'hardBreak', 'pageBreak'}:
        return {'type': node_type}

    cleaned = {'type': node_type}
    attrs = _clean_attrs(node_type, node.get('attrs'))
    if attrs:
        cleaned['attrs'] = attrs
    content = node.get('content')
    if content is None:
        content = []
    if not isinstance(content, list):
        raise _invalid('Node content must be a list.')
    children = []
    for child in content:
        cleaned_child = _clean_node(child, depth + 1, ALLOWED_CHILDREN[node_type])
        if cleaned_child is not None:
            children.append(cleaned_child)
    if children:
        cleaned['content'] = children
    elif node_type in {'bulletList', 'orderedList', 'listItem', 'blockquote'}:
        # ProseMirror never produces these empty; drop them rather than store junk.
        return None
    return cleaned


def validate_doc(doc):
    """Return a sanitized copy of `doc` or raise DocError (invalid_doc / doc_too_large)."""
    try:
        size = len(json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    except (TypeError, ValueError, RecursionError):
        raise _invalid('The document is not valid JSON.')
    if size > MAX_DOC_BYTES:
        raise DocError('doc_too_large', 'This essay is too large to save (256 KB limit).', status=413)
    if not isinstance(doc, dict) or doc.get('type') != 'doc':
        raise _invalid('The document root must be a "doc" node.')
    cleaned = _clean_node(doc, 1, {'doc'})
    if not cleaned.get('content'):
        cleaned['content'] = [{'type': 'paragraph'}]
    return cleaned


def _inline_text(node):
    parts = []
    for child in node.get('content') or []:
        if child.get('type') == 'text':
            parts.append(child.get('text', ''))
        elif child.get('type') == 'hardBreak':
            parts.append('\n')
    return ''.join(parts)


def _blocks(node):
    """Yield (marker, text) for every leaf text block, in reading order."""
    node_type = node.get('type')
    if node_type in TEXT_BLOCKS:
        yield '', _inline_text(node)
        return
    if node_type in {'doc', 'blockquote'}:
        for child in node.get('content') or []:
            yield from _blocks(child)
        return
    if node_type in {'bulletList', 'orderedList'}:
        attrs = node.get('attrs') or {}
        start = attrs.get('start', 1) if node_type == 'orderedList' else 1
        for index, item in enumerate(node.get('content') or []):
            if node_type == 'orderedList':
                marker = f'{start + index}. '
            else:
                marker = '– ' if attrs.get('style') == 'dash' else '• '
            first = True
            for child_marker, text in _blocks(item):
                # The item's marker goes on its first block only.
                yield (marker if first else '') + child_marker, text
                first = False
        return
    if node_type == 'listItem':
        for child in node.get('content') or []:
            yield from _blocks(child)


class DocStats(NamedTuple):
    content: str
    word_count: int
    preview: str
    char_count: int
    char_count_no_spaces: int


def doc_stats(doc):
    """Plain text and counts of an already validated doc.

    Blocks are joined with a blank line and list items carry their marker, but
    the counts ignore the markers, and characters don't count line breaks, so a
    bullet list or a hard break doesn't inflate them. Empty blocks are skipped.
    """
    parts = []
    words = chars = visible = 0
    for marker, text in _blocks(doc):
        if not text.strip():
            continue
        parts.append(marker + text)
        words += len(WORD_PATTERN.findall(text))
        chars += len(text) - text.count('\n')
        visible += sum(1 for char in text if not char.isspace())
    content = '\n\n'.join(parts)
    return DocStats(content, words, make_preview(content), chars, visible)


def derive(doc):
    """Return (content, word_count, preview) for an already validated doc."""
    stats = doc_stats(doc)
    return stats.content, stats.word_count, stats.preview


def text_from_doc(doc):
    return derive(doc)[0]


def count_words(text):
    return len(WORD_PATTERN.findall(text or ''))


def make_preview(text):
    flat = WHITESPACE_PATTERN.sub(' ', text or '').strip()
    if len(flat) <= PREVIEW_CHARS:
        return flat
    cut = flat[:PREVIEW_CHARS]
    if ' ' in cut[PREVIEW_CHARS // 2:]:
        cut = cut[:cut.rindex(' ')]
    return cut.rstrip() + '…'


def doc_from_text(content):
    """Rebuild a plain document from legacy text: blank lines split paragraphs."""
    text = clean_text(content).replace('\r\n', '\n').replace('\r', '\n').strip('\n')
    paragraphs = []
    for block in BLANK_LINE_PATTERN.split(text):
        if not block.strip():
            continue
        inline = []
        for index, line in enumerate(block.split('\n')):
            if index:
                inline.append({'type': 'hardBreak'})
            if line:
                inline.append({'type': 'text', 'text': line})
        paragraphs.append({'type': 'paragraph', 'content': inline})
    return {'type': 'doc', 'content': paragraphs or [{'type': 'paragraph'}]}


def tab_doc(tab):
    """The tab's doc, rebuilt from `content` when it is null (never saved here)."""
    return tab.doc if tab.doc is not None else doc_from_text(tab.content)


def canonical_json(value):
    """Sorted keys, no spaces and ASCII only, so both sides hash identical bytes.

    ASCII output also means string offsets are the same in Python and in
    JavaScript's UTF-16 strings, which block patches rely on.
    """
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def doc_hash(doc):
    return hashlib.sha256(canonical_json(doc).encode('ascii')).hexdigest()


def _resync(detail):
    return DocError('resync', detail, status=409)


def apply_ops(blocks, ops):
    """Return a new list of top-level blocks with `ops` applied to `blocks`.

    Every op addresses `blocks` by index (`at`), in ascending, non-overlapping order:
      {"at": i, "delete": n, "insert": [block, ...]}  replace blocks[i:i+n]
      {"at": i, "patch": [prefix, suffix, middle]}   replace blocks[i] by
          canonical[:prefix] + middle + canonical[len - suffix:] (parsed back)
    Ops that don't fit `blocks` raise DocError('resync'): the client's base
    differs from the stored document and it has to send the whole doc.
    """
    result = []
    cursor = 0
    for op in ops:
        at = op['at']
        if at < cursor or at > len(blocks):
            raise _resync('Block ops are out of order or out of range.')
        result.extend(blocks[cursor:at])
        if 'patch' in op:
            if at >= len(blocks):
                raise _resync('A block patch points past the end of the document.')
            prefix, suffix, middle = op['patch']
            old = canonical_json(blocks[at])
            if prefix + suffix > len(old):
                raise _resync('A block patch does not fit the stored block.')
            try:
                result.append(json.loads(old[:prefix] + middle + old[len(old) - suffix:]))
            except (ValueError, RecursionError):
                raise _resync('A block patch does not produce valid JSON.')
            cursor = at + 1
        else:
            if at + op['delete'] > len(blocks):
                raise _resync('Block ops delete past the end of the document.')
            result.extend(op['insert'])
            cursor = at + op['delete']
    result.extend(blocks[cursor:])
    return result


def apply_delta(base_doc, ops, expected_hash):
    """Apply block ops to a stored (already valid) doc -> (validated doc, its hash).

    The hash is checked before validation, so a client whose base differs from
    the stored doc gets a resync rather than a misleading validation error.
    """
    candidate = {'type': 'doc', 'content': apply_ops(base_doc.get('content') or [], ops)}
    try:
        matches = doc_hash(candidate) == expected_hash
    except (TypeError, ValueError, RecursionError):
        matches = False
    if not matches:
        raise _resync('The document does not match the saved version.')
    doc = validate_doc(candidate)
    # Validation only rewrites what the client's normaliser missed; then the stored hash differs.
    return doc, (expected_hash if doc == candidate else doc_hash(doc))
