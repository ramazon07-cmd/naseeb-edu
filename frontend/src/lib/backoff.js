// Retry delays with "full jitter": a uniformly random wait between 0 and an
// exponentially growing ceiling. Clients that failed together (a deploy, a
// flaky network) then retry spread out instead of in synchronized waves.

// ceiling for the attempt-th retry (0-based): base · 2^attempt, capped.
export function backoffCeiling(attempt, { base = 1000, cap = 30000 } = {}) {
  return Math.min(cap, base * 2 ** Math.max(0, attempt))
}

export function fullJitter(ceiling, random = Math.random) {
  return Math.floor(random() * Math.max(0, ceiling))
}

export function backoffDelay(attempt, options = {}, random = Math.random) {
  return fullJitter(backoffCeiling(attempt, options), random)
}

// Idempotent reads (GET) are retried a couple of times on errors that are
// usually transient: no connection, 429, 502, 503, 504.
export const REQUEST_RETRY = { retries: 2, base: 500, cap: 4000 }
const RETRYABLE_STATUS = new Set([0, 429, 502, 503, 504])

// Retry-After as seconds or an HTTP date -> ms, or null when absent/invalid.
export function retryAfterMs(value, now = Date.now()) {
  if (value == null || value === '') return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000)
  const date = Date.parse(value)
  return Number.isFinite(date) ? Math.max(0, date - now) : null
}

// -> ms to wait before retry number `attempt` (0-based), or null for "don't retry".
// A server asking for a longer pause than `cap` is not retried automatically.
export function requestRetryDelay(attempt, status, retryAfter = null, options = REQUEST_RETRY, random = Math.random) {
  const { retries, base, cap } = { ...REQUEST_RETRY, ...options }
  if (attempt >= retries || !RETRYABLE_STATUS.has(status)) return null
  const asked = retryAfterMs(retryAfter)
  if (asked != null) return asked <= cap ? asked : null
  return backoffDelay(attempt, { base, cap }, random)
}
