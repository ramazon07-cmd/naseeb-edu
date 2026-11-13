// Coach result helpers (pure).
import { normalizeText } from './anchors.js'

export const NOTE_KINDS = [
  { id: 'reflect', tab: 'Reflect', label: 'Reflection' },
  { id: 'specific', tab: 'Specifics', label: 'Specifics' },
  { id: 'clarity', tab: 'Clarity', label: 'Clarity' },
  { id: 'strength', tab: 'Strengths', label: 'Strength' },
]

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

// Criteria keys and labels differ per essay type; the backend rubric files
// (backend/apps/admissions/essay_lab/rubrics/*.md) own the keys. Labels below
// are interface text (translated in translations/essayLab.js).
const PERSONAL_LABELS = {
  reflection: 'Reflection and insight',
  specificity: 'Specific detail and scene',
  voice: 'Individual voice',
  structure: 'Structure and focus',
  prompt_fit: 'Fit to the prompt and length',
}
const SUPPLEMENT_LABELS = {
  fit_specificity: 'Specificity to the school, program or prompt',
  reflection: 'Reflection and personal connection',
  evidence: 'Concrete evidence from your life',
  voice: 'Individual voice',
  concision: 'Focus and use of the word limit',
}
const SCHOLARSHIP_LABELS = {
  goals_impact: 'Goals and intended impact',
  evidence: 'Evidence of merit or need, with specifics',
  mission_fit: 'Fit to the scholarship’s mission',
  reflection_voice: 'Reflection and individual voice',
  prompt_fit: 'Fit to the prompt and length',
}
const FREE_WRITING_LABELS = {
  clarity_idea: 'Clarity of the central idea',
  specificity: 'Specific detail and scene',
  voice: 'Individual voice',
  structure: 'Structure and flow',
}
export const CRITERIA_LABELS = {
  personal_statement: PERSONAL_LABELS,
  free_writing: FREE_WRITING_LABELS,
  supplement: SUPPLEMENT_LABELS,
  scholarship: SCHOLARSHIP_LABELS,
}
// Results saved before rubric versions carry no `rubric_version`; they keep their old short labels.
export const LEGACY_LABELS = {
  reflection: 'Reflection',
  specificity: 'Specific details',
  voice: 'Your voice',
  structure: 'Structure',
  prompt_fit: 'Answers the question',
}
export const SCORE_KEYS = Object.entries(LEGACY_LABELS).map(([key, label]) => ({ key, label }))

export const RUBRIC_NAMES = {
  personal_statement: 'Personal statement',
  free_writing: 'Free writing',
  supplement: 'Supplemental essay',
  scholarship: 'Scholarship essay',
}

// 'fit_specificity' -> 'Fit specificity'
export function labelFromKey(key) {
  const text = String(key ?? '').replace(/[_-]+/g, ' ').trim()
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : ''
}

export function resultMode(check) {
  return (check?.result?.mode || check?.mode) === 'safety' ? 'safety' : 'check'
}

export function isCached(check) {
  return Boolean(check?.cached ?? check?.result?.cached)
}

export function criterionLabel(type, key, legacy = false) {
  if (legacy && LEGACY_LABELS[key]) return LEGACY_LABELS[key]
  return CRITERIA_LABELS[type]?.[key] || PERSONAL_LABELS[key] || labelFromKey(key)
}

// -> [{ key, label, value (1-4), band, evidence }] for whatever keys the result carries,
// in the order the backend sent them. Values outside 1-4 are skipped.
export function criteriaRows(result) {
  const scores = result?.scores
  if (!scores || typeof scores !== 'object') return []
  const legacy = result.rubric_version == null
  const evidence = result.score_evidence && typeof result.score_evidence === 'object' ? result.score_evidence : {}
  return Object.keys(scores).flatMap((key) => {
    const value = Number(scores[key])
    if (!Number.isInteger(value) || value < 1 || value > 4) return []
    const quote = typeof evidence[key] === 'string' ? evidence[key].trim() : ''
    return [{ key, label: criterionLabel(result.type, key, legacy), value, band: scoreBand(value), evidence: quote }]
  })
}

export function rubricName(result) {
  return result?.rubric_name || RUBRIC_NAMES[result?.type] || ''
}

// -> { average (1-4), percent (0-100), band } or null.
// Uses the server's integer `overall` (0-100) when present, else averages the 1-4 scores
// of old-shape results.
export function overallScore(result) {
  const server = Number(result?.overall)
  if (result && result.overall != null && Number.isFinite(server) && server >= 0 && server <= 100) {
    const percent = Math.round(server)
    const average = 1 + (percent * 3) / 100
    return { average, percent, band: scoreBand(average) }
  }
  const values = criteriaRows(result?.scores ? result : { scores: result }).map((row) => row.value)
  if (!values.length) return null
  const average = values.reduce((sum, value) => sum + value, 0) / values.length
  return { average, percent: Math.round((average / 4) * 100), band: scoreBand(average) }
}

// Safety result: calm message plus the resource text the backend sends
// (`resource` string, or `resources` string | array of string | {label, text}). No scores.
export function safetyContent(result) {
  const raw = result?.resources ?? result?.resource ?? result?.helpline
  const list = Array.isArray(raw) ? raw : raw ? [raw] : []
  const resources = list.map((item) => (typeof item === 'string' ? { label: '', text: item } : { label: item?.label || '', text: item?.text || '' })).filter((item) => item.text)
  return { message: typeof result?.message === 'string' ? result.message : '', resources }
}

// The editor highlights only notes, so an evidence quote can be jumped to when a note
// quotes the same words. -> note or null.
export function noteForQuote(notes, quote) {
  const wanted = normalizeText(quote).trim().toLowerCase()
  if (!wanted) return null
  return (notes || []).find((note) => note?.id && normalizeText(note.quote).trim().toLowerCase() === wanted) || null
}

export function kindOf(note) {
  return NOTE_KINDS.find((kind) => kind.id === note?.kind) || NOTE_KINDS[0]
}

// Where a check's feedback came from. The backend stores 'local' when it ran the
// built-in rules instead of an AI model; anything else names the model used.
export const LOCAL_COACH_MODEL = 'local'

export function coachSource(check) {
  if (!check) return null
  return !check.model || check.model === LOCAL_COACH_MODEL ? 'rules' : 'ai'
}
