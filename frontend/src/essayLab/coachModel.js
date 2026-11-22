// Coach result helpers (pure). Rules: docs/essay-coach-rules.md.

export const CRITERIA = [
  { key: 'reflection', label: 'Reflection' },
  { key: 'specificity', label: 'Specific details' },
  { key: 'voice', label: 'Your voice' },
  { key: 'structure', label: 'Structure' },
  { key: 'prompt_fit', label: 'Answers the prompt' },
]

// Kept for callers that only need the five score keys.
export const SCORE_KEYS = CRITERIA

export const CRITERION_KEYS = CRITERIA.map((item) => item.key)
export const STRENGTHS = 'strengths'

export const criterionLabel = (key) => CRITERIA.find((item) => item.key === key)?.label || 'Reflection'

// The supplement rubric has no "Structure": its fifth criterion (API key `structure`) judges focus and
// use of the word limit. Results carry `rubric` ('personal_statement' | 'supplement'); old ones have none.
export const SUPPLEMENT_RUBRIC = 'supplement'
const SUPPLEMENT_LABELS = { structure: 'Focus and length' }
const SUPPLEMENT_EXPLAIN = { structure: 'Does it use the space well, with no sentence that only repeats?' }

export function criteriaFor(rubric) {
  if (rubric !== SUPPLEMENT_RUBRIC) return CRITERIA
  return CRITERIA.map((item) => ({ ...item, label: SUPPLEMENT_LABELS[item.key] || item.label }))
}

export const explainFor = (rubric, key, explain) => (rubric === SUPPLEMENT_RUBRIC && SUPPLEMENT_EXPLAIN[key]) || explain[key]

// Old checks (no version 2) used these kinds.
const LEGACY_CRITERION = { reflect: 'reflection', specific: 'specificity', clarity: 'structure', strength: STRENGTHS }

// `keys`/`fallback` let another rubric (recommendation letters) reuse the normalizer.
export function criterionOf(note, keys = CRITERION_KEYS, fallback = 'reflection') {
  const direct = note?.criterion
  if (keys.includes(direct)) return direct
  return LEGACY_CRITERION[note?.kind] || fallback
}

// 1-4 -> level word
const LEVELS = ['Emerging', 'Developing', 'Solid', 'Strong']
export function levelWord(score) {
  const value = Math.round(Number(score))
  if (!Number.isFinite(value) || value < 1) return null
  return LEVELS[Math.min(4, value) - 1]
}

// overall 0-100 -> headline, per contract.
export function headline(overall) {
  const value = Number(overall)
  if (overall === null || overall === undefined || !Number.isFinite(value)) return null
  if (value <= 50) return 'Early depth'
  if (value <= 70) return 'Developing depth'
  if (value <= 80) return 'Solid depth'
  return 'Strong depth'
}

// Band edges of the notes (50/51, 60/61, 70/71, 80/81): within this many points the score can
// flip between two checks of nearly the same text.
export const BAND_EDGES = [50, 60, 70, 80]
export const NEAR_EDGE_POINTS = 3

export function nearBandEdge(overall) {
  if (overall === null || overall === undefined) return false
  const value = Number(overall)
  if (!Number.isFinite(value)) return false
  return BAND_EDGES.some((edge) => Math.abs(value - edge) <= NEAR_EDGE_POINTS)
}

export function deltaSince(overall, previous) {
  const now = Number(overall)
  const before = Number(previous)
  if (previous == null || overall == null || !Number.isFinite(now) || !Number.isFinite(before)) return null
  const change = Math.round(now - before)
  return change > 0 ? change : null
}

const BANDS = [
  { min: 3.5, label: 'Excellent', tone: 'good' },
  { min: 2.75, label: 'Strong', tone: 'good' },
  { min: 1.75, label: 'Developing', tone: 'warn' },
  { min: 0, label: 'Getting started', tone: 'warn' },
]

export function scoreBand(value) {
  const score = Number(value)
  if (!Number.isFinite(score) || score <= 0) return { label: 'Not scored', tone: 'neutral' }
  return BANDS.find((band) => score >= band.min)
}

// Fallback for old checks: the plain average of whatever scores exist.
// -> { average (1-4), percent (0-100), band } or null
export function overallScore(scores) {
  const values = CRITERIA.map(({ key }) => Number(scores?.[key])).filter((value) => value >= 1 && value <= 4)
  if (!values.length) return null
  const average = values.reduce((sum, value) => sum + value, 0) / values.length
  return { average, percent: Math.round((average / 4) * 100), band: scoreBand(average) }
}

// Where a check's feedback came from. The server sends `source` ("ai" | "rules");
// older checks only carry the model name ('local' = built-in rules).
export const LOCAL_COACH_MODEL = 'local'

export function coachSource(check) {
  if (!check) return null
  if (check.source === 'ai' || check.source === 'rules') return check.source
  return !check.model || check.model === LOCAL_COACH_MODEL ? 'rules' : 'ai'
}

export const SCORE_HIDDEN = ['short', 'calibrating']
const LENGTH_FAILURES = ['over_limit', 'under_minimum']
// The one line shown instead of the score ring when a result has no shown score.
export const SCORE_HIDDEN_TEXT = {
  short: 'Short answers get questions, not a score.',
  calibrating: 'Scores for this type are not shown yet.',
}

// One shape for the panel, whatever version the stored check has.
// -> { version2, scored, overall, scores, summary, suggestions, strengths, notesLocked, notes }
export function normalizeCheck(check, { keys = CRITERION_KEYS, fallback = 'reflection' } = {}) {
  const result = check?.result
  if (!result) return null
  const version2 = Number(result.version) === 2
  const rawNotes = Array.isArray(result.notes) ? result.notes.filter((note) => note && note.id) : []
  const strengths = []
  const notes = []
  for (const note of rawNotes) {
    const criterion = criterionOf(note, keys, fallback)
    if (!version2 && criterion === STRENGTHS) {
      strengths.push({ id: String(note.id), criterion: null, quote: note.quote || '', text: note.question || '' })
      continue
    }
    notes.push({
      id: String(note.id),
      criterion: criterion === STRENGTHS ? fallback : criterion,
      quote: note.quote || '',
      question: note.question || '',
      context: String(version2 ? note.context || '' : note.context || note.why || '').trim(),
      priority: version2 && Boolean(note.priority),
    })
  }
  const listed = (Array.isArray(result.strengths) ? result.strengths : []).filter(Boolean)
  listed.forEach((item, index) => {
    if (typeof item === 'string') strengths.push({ id: `s${index + 1}`, criterion: null, quote: '', text: item })
    else strengths.push({ id: String(item.id || `s${index + 1}`), criterion: item.criterion || null, quote: item.quote || '', text: item.text || '' })
  })
  let overall = null
  if (version2) overall = Number.isFinite(Number(result.overall)) && result.overall !== null ? Math.round(Number(result.overall)) : null
  else overall = overallScore(result.scores)?.percent ?? null
  return {
    version2,
    scored: version2 && result.scored !== false && overall !== null,
    overall,
    scores: result.scores || {},
    summary: result.summary || '',
    suggestions: (Array.isArray(result.suggestions) ? result.suggestions : []).filter(Boolean),
    strengths,
    notesLocked: version2 && Boolean(result.notes_locked),
    notes,
    rubric: version2 && typeof result.rubric === 'string' ? result.rubric : null,
    // 'current_danger' (not scored: a calm message) | 'past_hardship' (scored, one optional support line)
    safety: version2 && (result.safety === 'current_danger' || result.safety === 'past_hardship') ? result.safety : null,
    helpline: version2 && typeof result.helpline === 'string' ? result.helpline.trim() : '',
    // No question was given: fit to the prompt was set to 3 by the server, not judged.
    fitDefault: version2 && Boolean(result.fit_default),
    // 'short' (a short answer: questions, no score) | 'calibrating' (scores for this type are not shown yet)
    scoreHidden: version2 && SCORE_HIDDEN.includes(result.score_hidden) ? result.score_hidden : null,
    // A personal statement whose length failed: 'over_limit' | 'under_minimum' (fit counts as 1).
    length: version2 && LENGTH_FAILURES.includes(result.length) ? result.length : null,
  }
}

// --- Note states -------------------------------------------------------------
// States are { [note_id]: 'done' | 'dismissed' | 'gone' }; 'open' removes the entry.
export function applyNoteState(states, noteId, state) {
  const next = { ...(states || {}) }
  if (state === 'done' || state === 'dismissed' || state === 'gone') next[noteId] = state
  else delete next[noteId]
  return next
}

// Notes that still need an answer: not marked, and their sentence is still in the text.
export function openNotes(notes, states, anchored) {
  return (notes || []).filter((note) => !states?.[note.id] && anchored?.has(note.id))
}

// After a refetch: the server's states, except notes whose own save is still in flight.
export function mergeNoteStates(server, local, inflight) {
  const next = { ...(server || {}) }
  for (const id of inflight || []) {
    if (local?.[id]) next[id] = local[id]
    else delete next[id]
  }
  return next
}

// Notes marked done/dismissed (shown in the collapsed "Done" row).
export function doneNotes(notes, states) {
  return (notes || []).filter((note) => states?.[note.id] === 'done' || states?.[note.id] === 'dismissed')
}

// Notes whose sentence is gone count as resolved.
export function goneNotes(notes, states, anchored) {
  return (notes || []).filter((note) => states?.[note.id] === 'gone' || (!states?.[note.id] && !anchored?.has(note.id)))
}

// What the client should tell the server after the text moved: notes whose sentence vanished
// become 'gone'; 'gone' notes whose sentence is back are reopened. -> [{ id, state }]
export function noteStateUpdates(notes, states, anchored) {
  const updates = []
  for (const note of notes || []) {
    const mark = states?.[note.id]
    const found = Boolean(anchored?.has(note.id))
    if (mark === 'gone' && found) updates.push({ id: note.id, state: 'open' })
    else if (!mark && !found) updates.push({ id: note.id, state: 'gone' })
  }
  return updates
}

// "Check again" state: why it is blocked, or null when it can run.
// -> 'notes_open' | 'unchanged' | null
export function recheckBlock({ hasCheck, openCount, changed, inputChanged = false }) {
  if (!hasCheck || inputChanged) return null // a new question/type/word limit is checked without the notes/text rules
  if (openCount > 0) return 'notes_open'
  if (!changed) return 'unchanged'
  return null
}

// --- Fingerprint ---------------------------------------------------------------
// Same as the server: NFKC, lower-case, curly quotes to straight, drop every
// character that is not a letter, digit or whitespace, collapse whitespace, trim.
// Python's str.isspace() set (not JS \s, which differs, e.g. U+FEFF is not whitespace in Python).
const PY_SPACE = '\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const NOT_KEPT = new RegExp(`[^\\p{L}\\p{N}${PY_SPACE}]`, 'gu')
const SPACE_RUN = new RegExp(`[${PY_SPACE}]+`, 'gu')
const SPACE_EDGES = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, 'gu')
const SINGLE_QUOTES = /[‘’‚‛′‵]/g
const DOUBLE_QUOTES = /[“”„‟″‶«»]/g

export function normalizeForFingerprint(text) {
  return String(text ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(SINGLE_QUOTES, "'")
    .replace(DOUBLE_QUOTES, '"')
    .replace(NOT_KEPT, '')
    .replace(SPACE_RUN, ' ')
    .replace(SPACE_EDGES, '')
}

// -> sha256 hex of the normalized text, or null when crypto.subtle is unavailable.
export async function textFingerprint(text) {
  const subtle = globalThis.crypto?.subtle
  if (!subtle) return null
  const bytes = new TextEncoder().encode(normalizeForFingerprint(text))
  const digest = await subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

// The prompt, type or word limit changed since the check (only when the server sends both hashes).
export function inputChangedSince(check, currentHash) {
  return Boolean(check?.input_hash && currentHash && check.input_hash !== currentHash)
}

// Server messages for the footer (409s and the like).
export function serverNotice(error) {
  const code = error?.details?.code || error?.details?.detail
  if (code === 'notes_open') return 'notes_open'
  if (code === 'too_small_change') return 'too_small_change'
  return null
}
