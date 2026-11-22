// Pure helpers for the counselor letter workspace (no React, runs under node).
// Rules: docs/letter-coach-rules.md. The note/score logic is shared with Essay Coach (coachModel.js).
import { buildIndex, findAllQuotes } from '../essayLab/anchors.js'
import { normalizeCheck } from '../essayLab/coachModel.js'

export const LETTER_CRITERIA = [
  { key: 'evidence', label: 'Specific evidence', explain: 'Real moments, projects and results you saw yourself.' },
  { key: 'insight', label: 'Insight', explain: 'What the student’s actions say about who they are.' },
  { key: 'context', label: 'Basis and context', explain: 'How you know the student, and the school context a foreign reader needs.' },
  { key: 'structure', label: 'Structure and length', explain: 'A clear opening, a focused middle and a firm recommendation.' },
  { key: 'voice', label: 'Your voice', explain: 'Does it sound like you, not a template?' },
]
export const LETTER_KEYS = LETTER_CRITERIA.map((item) => item.key)
export const LETTER_NORMALIZE = { keys: LETTER_KEYS, fallback: 'evidence' }
export const normalizeLetterCheck = (check) => normalizeCheck(check, LETTER_NORMALIZE)
export const letterCriterionLabel = (key) => LETTER_CRITERIA.find((item) => item.key === key)?.label || LETTER_CRITERIA[0].label

// Not scored, not notes: the reader notes, the sensitive-content notes, the copy check and the safety
// flag the server puts next to the notes of a check (result.reader_notes / sensitive / copy / safety).
// The wording of the sensitive notes is fixed here so it can be shown in every language.
export const SENSITIVE_TEXT = {
  health: 'This names a health matter of a minor. Have the student and family agreed to share it, and does the reader need it?',
  discipline: 'If this explains an event on the record, does the letter say what happened afterwards in your own observation?',
}
export const READER_CRITERION = 'reader'
export const SENSITIVE_CRITERION = 'sensitive'

export function letterExtras(check) {
  const result = check?.result
  if (!result || typeof result !== 'object') return { readerNotes: [], sensitive: [], copy: null, safety: false }
  const readerNotes = (Array.isArray(result.reader_notes) ? result.reader_notes : [])
    .filter((item) => item && item.id && item.quote && item.question)
    .map((item) => ({ id: String(item.id), criterion: READER_CRITERION, quote: String(item.quote), question: String(item.question) }))
  const sensitive = (Array.isArray(result.sensitive) ? result.sensitive : [])
    .filter((item) => item && SENSITIVE_TEXT[item.kind])
    .map((item) => ({ id: `sx-${item.kind}`, criterion: SENSITIVE_CRITERION, kind: item.kind, quote: String(item.quote || ''), question: SENSITIVE_TEXT[item.kind] }))
  const percent = Math.round(Number(result.copy?.percent))
  const copy = result.copy && Number.isFinite(percent) && percent >= 30 && result.copy.date ? { percent: Math.min(100, percent), date: String(result.copy.date) } : null
  return { readerNotes, sensitive, copy, safety: result.safety === true }
}

export const LETTER_MAX_CHARS = 20000
export const AI_DAILY_LIMIT = 20

export const conflictError = (message) => Object.assign(new Error(message), { details: { code: 'conflict' } })
export const normalizeNewlines = (text) => String(text ?? '').replace(/\r\n?/g, '\n')

export const wordCount = (text) => (String(text ?? '').trim() ? String(text).trim().split(/\s+/).length : 0)

// --- Where the notes' sentences are in the text ----------------------------------
// notes: [{ id, quote }]; hints: Map id -> previous start offset (kept across edits so a note
// stays on the same sentence when it is repeated). Two notes never take the same occurrence
// while a free one exists. -> Map id -> { from, to }
// The sentence (or line) around a short hit: ends at . ! ? or a line break, quotes and brackets included.
export function sentenceAround(text, from, to) {
  const source = String(text ?? '')
  let start = from
  while (start > 0) {
    const before = source[start - 1]
    if (before === '\n') break
    if (/[.!?]/.test(before) && /\s/.test(source[start] ?? ' ') && start - 1 < from) break
    start -= 1
  }
  while (start < from && /\s/.test(source[start])) start += 1
  let end = to
  while (end < source.length && source[end] !== '\n') {
    if (/[.!?]/.test(source[end])) {
      end += 1
      while (end < source.length && /["'”’)\]]/.test(source[end])) end += 1
      break
    }
    end += 1
  }
  while (end > to && /\s/.test(source[end - 1])) end -= 1
  return { from: start, to: end }
}

export function locateNotes(text, notes, hints = new Map()) {
  const located = new Map()
  const list = (notes || []).filter((note) => note?.quote)
  if (!list.length) return located
  const index = buildIndex(text)
  const taken = []
  for (const note of list) {
    const hits = findAllQuotes(index, note.quote)
    if (!hits.length) continue
    const free = hits.filter((hit) => !taken.some((other) => other.from === hit.from && other.to === hit.to))
    const pool = free.length ? free : hits
    const hint = hints.get(note.id)
    let pick = pool[0]
    if (hint != null) {
      let best = Infinity
      for (const hit of pool) {
        const distance = Math.abs(hit.from - hint)
        if (distance < best) { best = distance; pick = hit }
      }
    }
    taken.push(pick)
    const tiny = wordCount(text.slice(pick.from, pick.to)) <= 2
    located.set(note.id, tiny ? sentenceAround(text, pick.from, pick.to) : pick)
  }
  return located
}

// marks: [{ id, from, to, criterion }] -> text split at every mark edge:
// [{ text, from, to, ids: [], criterion }] (criterion of the active or first mark covering it, else null).
export function mirrorSegments(text, marks, activeId = null) {
  const source = String(text ?? '')
  const valid = (marks || []).filter((mark) => Number.isInteger(mark.from) && Number.isInteger(mark.to) && mark.to > mark.from && mark.from >= 0 && mark.from < source.length)
    .map((mark) => ({ ...mark, to: Math.min(mark.to, source.length) }))
  const points = new Set([0, source.length])
  for (const mark of valid) { points.add(mark.from); points.add(mark.to) }
  const sorted = [...points].sort((a, b) => a - b)
  const segments = []
  for (let i = 0; i < sorted.length - 1; i += 1) {
    const from = sorted[i]
    const to = sorted[i + 1]
    if (to <= from) continue
    const covering = valid.filter((mark) => mark.from <= from && mark.to >= to)
    const lead = covering.find((mark) => mark.id === activeId) || covering[0]
    segments.push({ text: source.slice(from, to), from, to, ids: covering.map((mark) => mark.id), criterion: lead ? lead.criterion : null, active: covering.some((mark) => mark.id === activeId) })
  }
  return segments
}

// The note under the caret (the active one wins when several overlap), or null.
export function noteAt(located, offset, activeId = null) {
  let found = null
  for (const [id, range] of located) {
    if (offset < range.from || offset > range.to) continue
    if (id === activeId) return id
    if (found === null) found = id
  }
  return found
}

// --- Inserting text from the Ideas tab ----------------------------------------------
// -> { body, caret } or null when it would pass the length limit.
export function insertAtCaret(body, start, end, text, max = LETTER_MAX_CHARS) {
  const from = Math.max(0, Math.min(start ?? body.length, body.length))
  const to = Math.max(from, Math.min(end ?? from, body.length))
  const before = body.slice(0, from)
  const after = body.slice(to)
  const lead = before && !/\s$/.test(before) ? ' ' : ''
  const trail = after && !/^\s/.test(after) ? ' ' : ''
  const next = `${before}${lead}${text}${trail}${after}`
  if (next.length > max) return null
  return { body: next, caret: before.length + lead.length + text.length }
}

export const fillStudent = (text, name) => String(text ?? '').replaceAll('[Student]', name || '[Student]')

// A neutral line for a profile fact: "Title: detail."
export function factLine(item) {
  const title = String(item?.title ?? '').trim().replace(/[.\s]+$/, '')
  const detail = String(item?.detail ?? '').trim().replace(/[.\s]+$/, '')
  if (!title && !detail) return ''
  return `${title}${title && detail ? ': ' : ''}${detail}.`
}

// Check text may carry "[Student]"; show the first name instead.
export function fillCheckText(model, name) {
  if (!model) return model
  const fill = (text) => fillStudent(text, name)
  return {
    ...model,
    summary: fill(model.summary),
    suggestions: model.suggestions.map(fill),
    strengths: model.strengths.map((item) => ({ ...item, text: fill(item.text) })),
    notes: model.notes.map((note) => ({ ...note, question: fill(note.question), context: fill(note.context) })),
  }
}

export const fillExtras = (extras, name) => ({ ...extras, readerNotes: extras.readerNotes.map((note) => ({ ...note, question: fillStudent(note.question, name) })) })

export const factsOf = (items) => (items || []).filter((item) => item?.kind === 'fact')
// AI ideas are questions to the author (each cites one profile fact); they are never inserted into the letter.
export const aiIdeasOf = (items) => (items || []).filter((item) => item?.kind === 'question' && item.text)
// Only a profile fact has a "+" (it inserts the neutral "Title: detail." line).
export const canInsert = (item) => item?.kind === 'fact'

// The Check button after an error: hidden only when it can never work (not a counselor, or the server says
// AI is switched off: `details.ai_available` false). A provider failure stays retryable.
export function checkAvailability(error) {
  const code = error?.code
  const unavailable = code === 'counselors_only' || Boolean(error?.off)
    || (code === 'coach_unavailable' && error?.details?.ai_available === false)
  return { unavailable, retry: code === 'coach_unavailable' && !unavailable }
}

// --- Header line ---------------------------------------------------------------------
export function recommenderSummary(form, { dueText = '', statusText = '' } = {}) {
  return [form.recommender_name, form.recommender_title, dueText, statusText].filter(Boolean)
}

// Fields whose change makes the server's input hash differ (title, relationship).
export const inputKeyOf = (form) => `${form.recommender_title ?? ''}|${form.relationship ?? ''}`
