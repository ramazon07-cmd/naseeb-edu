// Progress math for the Naseeb AI essay check. The check is one request with no
// progress events, so the bar is an honest estimate driven by elapsed time only:
// it eases toward CAP and reaches 100% only when the response lands.
export const DEFAULT_EXPECTED_MS = 45000
export const MIN_EXPECTED_MS = 15000
export const MAX_EXPECTED_MS = 90000
export const CAP = 0.92
export const HISTORY_KEY = 'naseeb.essayCheck.durations'
export const HISTORY_SIZE = 5

// Stage starts as a share of the expected duration.
export const STAGES = [
  { at: 0, label: 'Reading your essay' },
  { at: 0.2, label: 'Checking structure and content' },
  { at: 0.5, label: 'Scoring against the rubric' },
  { at: 0.8, label: 'Writing feedback' },
]

const finite = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0)
const expectedOf = (expectedMs) => Math.max(1, finite(expectedMs) || DEFAULT_EXPECTED_MS)

// 0..CAP, rising smoothly; slows down near the cap but keeps creeping so it never looks frozen.
export function progressFraction(elapsedMs, expectedMs = DEFAULT_EXPECTED_MS) {
  const elapsed = Math.max(0, finite(elapsedMs))
  return CAP * (1 - Math.exp((-2.3 * elapsed) / expectedOf(expectedMs)))
}

export function stageIndex(elapsedMs, expectedMs = DEFAULT_EXPECTED_MS) {
  const share = Math.max(0, finite(elapsedMs)) / expectedOf(expectedMs)
  let index = 0
  STAGES.forEach((stage, i) => { if (share >= stage.at) index = i })
  return index
}

// Seconds left (rounded up to a multiple of 5), or null once past the estimate.
export function secondsLeft(elapsedMs, expectedMs = DEFAULT_EXPECTED_MS) {
  const left = (expectedOf(expectedMs) - Math.max(0, finite(elapsedMs))) / 1000
  if (left <= 3) return null
  return Math.ceil(left / 5) * 5
}

export function expectedFromHistory(durations) {
  const clean = (Array.isArray(durations) ? durations : []).map(Number).filter((n) => Number.isFinite(n) && n > 0)
  if (!clean.length) return DEFAULT_EXPECTED_MS
  const average = clean.reduce((sum, n) => sum + n, 0) / clean.length
  return Math.min(MAX_EXPECTED_MS, Math.max(MIN_EXPECTED_MS, Math.round(average)))
}

function storage(store) {
  if (store) return store
  try { return globalThis.localStorage || null } catch { return null }
}

export function readDurations(store) {
  try {
    const raw = storage(store)?.getItem(HISTORY_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.map(Number).filter((n) => Number.isFinite(n) && n > 0).slice(-HISTORY_SIZE) : []
  } catch { return [] }
}

export function recordDuration(ms, store) {
  const value = Math.round(finite(ms))
  if (value < 2000) return // cache hits / instant failures say nothing about a real check
  try {
    const target = storage(store)
    if (!target) return
    target.setItem(HISTORY_KEY, JSON.stringify([...readDurations(target), Math.min(value, MAX_EXPECTED_MS * 2)].slice(-HISTORY_SIZE)))
  } catch { /* private mode / quota: the default estimate still works */ }
}

export function expectedDuration(store) {
  return expectedFromHistory(readDurations(store))
}

// Tracks the one pending check outside any component, so hiding the panel or
// entering focus mode neither restarts the bar nor records a bogus duration.
export function createCheckTimer({ now = () => Date.now(), store } = {}) {
  let pending = null
  return {
    start() { pending = { startedAt: now(), expected: expectedDuration(store) } },
    // Only a successful response is a real duration.
    succeed() { if (pending) recordDuration(now() - pending.startedAt, store); pending = null },
    fail() { pending = null },
    state() { return pending },
  }
}

export const checkTimer = createCheckTimer()
