// Finding Coach quotes in the essay text.
//
// The backend keeps a note only when its quote appears in the normalized
// essay text. Normalization: NFKC, curly -> straight
// quotes, whitespace runs -> one space. Here the same normalization is applied
// while remembering, for every normalized character, which original character
// range it came from, so a match can be turned back into editor positions.
// Quotes never span paragraphs, so the editor searches one textblock at a time.
// Framework-free: runs in the browser and under plain `node`.

const SINGLE_QUOTES = /[‘’‚‛′‵]/g
const DOUBLE_QUOTES = /[“”„‟″‶«»]/g
const WHITESPACE = /^\s+$/u
// A base character followed by combining marks is normalized as one unit so
// that NFKC can compose it (e + U+0301 -> é) exactly like a whole-string NFKC.
const CLUSTER = /\P{M}\p{M}*|\p{M}+/gsu

function foldQuotes(text) {
  return text.replace(SINGLE_QUOTES, "'").replace(DOUBLE_QUOTES, '"')
}

export function normalizeText(text) {
  return foldQuotes(String(text ?? '').normalize('NFKC')).replace(/\s+/gu, ' ')
}

// -> { norm, start, end } where norm[i] came from original[start[i], end[i]).
export function buildIndex(text) {
  const source = String(text ?? '')
  let norm = ''
  const start = []
  const end = []
  CLUSTER.lastIndex = 0
  let match
  while ((match = CLUSTER.exec(source))) {
    const cluster = match[0]
    const from = match.index
    const to = from + cluster.length
    const folded = foldQuotes(cluster.normalize('NFKC'))
    if (WHITESPACE.test(folded)) {
      if (norm.endsWith(' ')) {
        end[end.length - 1] = to // extend the collapsed run
        continue
      }
      norm += ' '
      start.push(from)
      end.push(to)
      continue
    }
    for (let i = 0; i < folded.length; i += 1) {
      norm += folded[i]
      start.push(from)
      end.push(to)
    }
  }
  return { text: source, norm, start, end }
}

const LIST_PREFIX = /^(?:[•–-]|\d+\.)\s+/

function allMatches(haystack, needle) {
  const found = []
  if (!needle) return found
  let at = haystack.indexOf(needle)
  while (at !== -1) {
    found.push(at)
    at = haystack.indexOf(needle, at + 1)
  }
  return found
}

// Find `quote` inside an index built with buildIndex. Returns original
// offsets { from, to } (to exclusive) or null. With several matches, the one
// closest to `hint` (an original offset) wins, which keeps a highlight on the
// same sentence when the student repeats a phrase elsewhere.
export function findQuote(index, quote, hint = null) {
  let needle = normalizeText(quote).trim()
  if (!needle || !index?.norm) return null
  let hits = allMatches(index.norm, needle)
  if (!hits.length && LIST_PREFIX.test(needle)) {
    // The plain text carries list prefixes ("• ", "1. ") that the editor doesn't.
    needle = needle.replace(LIST_PREFIX, '')
    hits = allMatches(index.norm, needle)
  }
  if (!hits.length) return null
  let best = hits[0]
  if (hint != null && hits.length > 1) {
    let bestDistance = Infinity
    for (const at of hits) {
      const distance = Math.abs(index.start[at] - hint)
      if (distance < bestDistance) { best = at; bestDistance = distance }
    }
  }
  return { from: index.start[best], to: index.end[best + needle.length - 1] }
}

// blocks: [{ index, offset }] where `offset` is the absolute position of the
// block's first character (for ProseMirror: textblock pos + 1).
// notes: [{ id, quote }]; hints: Map id -> previous absolute position.
// Returns Map id -> { from, to } in absolute positions; missing quotes are dropped.
export function locateQuotes(blocks, notes, hints = new Map()) {
  const located = new Map()
  for (const note of notes || []) {
    if (!note?.quote) continue
    const hint = hints.get(note.id)
    let best = null
    let bestDistance = Infinity
    for (const block of blocks) {
      const localHint = hint == null ? null : hint - block.offset
      const hit = findQuote(block.index, note.quote, localHint)
      if (!hit) continue
      const from = block.offset + hit.from
      const distance = hint == null ? 0 : Math.abs(from - hint)
      if (!best || distance < bestDistance) {
        best = { from, to: block.offset + hit.to }
        bestDistance = distance
        if (hint == null) break
      }
    }
    if (best) located.set(note.id, best)
  }
  return located
}
