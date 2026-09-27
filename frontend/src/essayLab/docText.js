// Plain-text derivation for Essay Lab documents (ProseMirror JSON).
//
// Must produce exactly the same text as the backend's `essay_lab/doc.py`
// (word counts, previews and Coach quotes all come from it). The shared cases
// live in backend/apps/admissions/essay_lab/fixtures/doc_text_cases.json and
// are copied to frontend/tests/fixtures/doc_text_cases.json.
// Rules:
//   - leaf text blocks (paragraph, heading, title, subtitle) are joined with "\n\n";
//     a pageBreak has no text;
//   - blocks whose text is only whitespace are skipped;
//   - a list item's marker ("• ", "– " for attrs.style "dash", "3. " counting
//     from attrs.start) goes on the item's first block only — even when that
//     block turns out to be empty and is skipped, exactly like the backend;
//   - hardBreak becomes "\n"; control characters are dropped;
//   - word_count counts \S+ runs in the block text, ignoring list markers;
//   - char_count counts code points of the block text except line breaks, and
//     char_count_no_spaces only the non-whitespace ones (markers never count).
// Whitespace is Python's `str.isspace` set, so \S means the same on both sides.
// Framework-free on purpose: it runs in the browser and under plain `node`.

export const TEXT_BLOCKS = new Set(['paragraph', 'heading', 'title', 'subtitle'])
export const ALLOWED_NODES = new Set([
  'doc', ...TEXT_BLOCKS, 'bulletList', 'orderedList', 'listItem', 'blockquote', 'pageBreak', 'text', 'hardBreak',
])
export const ALLOWED_MARKS = new Set(['bold', 'italic', 'underline', 'strike', 'textStyle', 'highlight', 'link'])
export const MAX_DOC_BYTES = 256 * 1024
export const MAX_DEPTH = 12
export const PREVIEW_CHARS = 160

const WS = '\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const WORD = new RegExp(`[^${WS}]+`, 'g')
const WHITESPACE_RUN = new RegExp(`[${WS}]+`, 'g')
const NOT_WHITESPACE = new RegExp(`[^${WS}]`, 'gu')
const ONLY_WHITESPACE = new RegExp(`^[${WS}]*$`)
const EDGE_WHITESPACE = new RegExp(`^[${WS}]+|[${WS}]+$`, 'g')
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g

export function cleanText(value) {
  return String(value ?? '').replace(CONTROL_CHARS, '')
}

function inlineText(node) {
  let out = ''
  for (const child of node.content || []) {
    if (child?.type === 'text') out += cleanText(child.text)
    else if (child?.type === 'hardBreak') out += '\n'
  }
  return out
}

// Pushes [marker, text] for every leaf text block, in reading order.
function collect(node, out) {
  const type = node?.type
  if (TEXT_BLOCKS.has(type)) {
    out.push(['', inlineText(node)])
  } else if (type === 'doc' || type === 'blockquote' || type === 'listItem') {
    for (const child of node.content || []) collect(child, out)
  } else if (type === 'bulletList' || type === 'orderedList') {
    const attrs = node.attrs || {}
    const start = type === 'orderedList' && Number.isInteger(attrs.start) ? attrs.start : 1
    ;(node.content || []).forEach((item, index) => {
      const marker = type === 'orderedList' ? `${start + index}. ` : attrs.style === 'dash' ? '– ' : '• '
      const inner = []
      collect(item, inner)
      inner.forEach(([childMarker, text], position) => out.push([(position === 0 ? marker : '') + childMarker, text]))
    })
  }
  return out
}

// -> { content, wordCount, preview, charCount, charCountNoSpaces }, same as the backend's doc_stats().
export function deriveText(doc) {
  const parts = []
  let wordCount = 0
  let charCount = 0
  let charCountNoSpaces = 0
  for (const [marker, text] of doc ? collect(doc, []) : []) {
    if (ONLY_WHITESPACE.test(text)) continue
    parts.push(marker + text)
    wordCount += countWords(text)
    const counts = countChars(text)
    charCount += counts.chars
    charCountNoSpaces += counts.noSpaces
  }
  const content = parts.join('\n\n')
  return { content, wordCount, preview: makePreview(content), charCount, charCountNoSpaces }
}

// Code points (like Python's len), without line breaks; and the non-whitespace ones.
export function countChars(text) {
  const value = String(text || '')
  let chars = 0
  for (const char of value) if (char !== '\n') chars += 1
  const visible = value.match(NOT_WHITESPACE)
  return { chars, noSpaces: visible ? visible.length : 0 }
}

export function docToText(doc) {
  return deriveText(doc).content
}

export function countWords(text) {
  if (!text) return 0
  const matches = String(text).match(WORD)
  return matches ? matches.length : 0
}

export function docWordCount(doc) {
  return deriveText(doc).wordCount
}

export function makePreview(text) {
  const flat = [...String(text || '').replace(WHITESPACE_RUN, ' ').replace(EDGE_WHITESPACE, '')]
  if (flat.length <= PREVIEW_CHARS) return flat.join('')
  let cut = flat.slice(0, PREVIEW_CHARS)
  const lastSpace = cut.lastIndexOf(' ')
  if (lastSpace >= PREVIEW_CHARS / 2) cut = cut.slice(0, lastSpace)
  return cut.join('').replace(new RegExp(`[${WS}]+$`), '') + '…'
}

export function docFromText(content) {
  const text = cleanText(content).replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/^\n+|\n+$/g, '')
  const paragraphs = []
  for (const block of text.split(/\n[ \t]*\n+/)) {
    if (ONLY_WHITESPACE.test(block)) continue
    const inline = []
    block.split('\n').forEach((line, index) => {
      if (index) inline.push({ type: 'hardBreak' })
      if (line) inline.push({ type: 'text', text: line })
    })
    paragraphs.push({ type: 'paragraph', content: inline })
  }
  return { type: 'doc', content: paragraphs.length ? paragraphs : [{ type: 'paragraph' }] }
}

// Byte size of the serialized doc (UTF-8), for the 256 KB limit and the 60 KB keepalive cap.
export function jsonByteSize(value) {
  const json = typeof value === 'string' ? value : JSON.stringify(value)
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(json).length
  return json.length
}

// Client-side mirror of the backend validation, so the editor can warn before a 400/413.
export function validateDoc(doc) {
  if (!doc || doc.type !== 'doc') return 'invalid_doc'
  let tooDeep = false
  let invalid = false
  const walk = (node, depth) => {
    if (invalid || tooDeep) return
    if (depth > MAX_DEPTH) { tooDeep = true; return }
    if (!ALLOWED_NODES.has(node?.type)) { invalid = true; return }
    for (const mark of node.marks || []) if (!ALLOWED_MARKS.has(mark?.type)) { invalid = true; return }
    for (const child of node.content || []) walk(child, depth + 1)
  }
  walk(doc, 1)
  if (invalid || tooDeep) return 'invalid_doc'
  if (jsonByteSize(doc) > MAX_DOC_BYTES) return 'doc_too_large'
  return null
}
