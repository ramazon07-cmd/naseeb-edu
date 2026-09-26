// Coach result helpers (pure).

export const SCORE_KEYS = [
  { key: 'reflection', label: 'Reflection' },
  { key: 'specificity', label: 'Specific details' },
  { key: 'voice', label: 'Your voice' },
  { key: 'structure', label: 'Structure' },
  { key: 'prompt_fit', label: 'Answers the question' },
]

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

// -> { average (1-4), percent (0-100), band } or null
export function overallScore(scores) {
  const values = SCORE_KEYS.map(({ key }) => Number(scores?.[key])).filter((value) => value >= 1 && value <= 4)
  if (!values.length) return null
  const average = values.reduce((sum, value) => sum + value, 0) / values.length
  return { average, percent: Math.round((average / 4) * 100), band: scoreBand(average) }
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
