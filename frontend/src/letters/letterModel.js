// Pure helpers for the counselor letter workspace (no React, runs under node).
// Rules: docs/letter-coach-rules.md. The note/score logic is shared with Essay Coach (coachModel.js).
import { buildIndex, findAllQuotes } from '../essayLab/anchors.js'
import { normalizeCheck } from '../essayLab/coachModel.js'

export const LETTER_CRITERIA = [
  { key: 'evidence', label: 'Specific evidence', explain: 'Real moments, projects and results you saw yourself.' },
  { key: 'insight', label: 'Insight', explain: 'What the student’s actions say about who they are.' },
  { key: 'context', label: 'Basis for comparison', explain: 'How the student compares with others you have taught or counselled.' },
  { key: 'structure', label: 'Structure and length', explain: 'A clear opening, a focused middle and a firm recommendation.' },
  { key: 'voice', label: 'Your voice', explain: 'Does it sound like you, not a template?' },
]
export const LETTER_KEYS = LETTER_CRITERIA.map((item) => item.key)
export const LETTER_NORMALIZE = { keys: LETTER_KEYS, fallback: 'evidence' }
export const normalizeLetterCheck = (check) => normalizeCheck(check, LETTER_NORMALIZE)
export const letterCriterionLabel = (key) => LETTER_CRITERIA.find((item) => item.key === key)?.label || LETTER_CRITERIA[0].label

export const LETTER_MAX_CHARS = 20000
export const AI_DAILY_LIMIT = 20

export const wordCount = (text) => (String(text ?? '').trim() ? String(text).trim().split(/\s+/).length : 0)

// --- Where the notes' sentences are in the text ----------------------------------
// notes: [{ id, quote }]; hints: Map id -> previous start offset (kept across edits so a note
// stays on the same sentence when it is repeated). Two notes never take the same occurrence
// while a free one exists. -> Map id -> { from, to }
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
    located.set(note.id, pick)
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

export const factsOf = (items) => (items || []).filter((item) => item?.kind === 'fact')
export const aiIdeasOf = (items) => (items || []).filter((item) => (item?.kind === 'sentence' || item?.kind === 'idea') && item.text)

// --- Header line ---------------------------------------------------------------------
export function recommenderSummary(form, { dueText = '', statusText = '' } = {}) {
  return [form.recommender_name, form.recommender_title, dueText, statusText].filter(Boolean)
}

// Fields whose change makes the server's input hash differ (title, relationship).
export const inputKeyOf = (form) => `${form.recommender_title ?? ''}|${form.relationship ?? ''}`
