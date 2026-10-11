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

// A 429 is retried when the server's Retry-After is at most this long; a longer
// pause (a lockout, a spent upload allowance) fails at once with its message.
export const RATE_LIMIT_WAIT_CAP = 8000

// -> ms to wait before retry number `attempt` (0-based), or null for "don't retry".
// A server asking for a longer pause than `cap` (RATE_LIMIT_WAIT_CAP for a 429)
// is not retried automatically.
export function requestRetryDelay(attempt, status, retryAfter = null, options = REQUEST_RETRY, random = Math.random) {
  const { retries, base, cap } = { ...REQUEST_RETRY, ...options }
  if (attempt >= retries || !RETRYABLE_STATUS.has(status)) return null
  const asked = retryAfterMs(retryAfter)
  if (asked != null) return asked <= (status === 429 ? Math.max(cap, RATE_LIMIT_WAIT_CAP) : cap) ? asked : null
  return backoffDelay(attempt, { base, cap }, random)
}

// A load that still came back 429 after its own retries ("Busy, retrying…"):
// ms until the next try of the whole load (at least the server's Retry-After,
// `error.retryAfter` in ms), or null to stop and show the error. A Retry-After
// longer than `maxWait` is not waited out; any other failure is never retried.
export const BUSY_RETRY = { retries: 3, base: 5000, cap: 30000, maxWait: 30000 }

export function busyRetryDelay(attempt, error, options = BUSY_RETRY, random = Math.random) {
  const { retries, base, cap, maxWait } = { ...BUSY_RETRY, ...options }
  const asked = Number(error?.retryAfter) || 0
  if (error?.status !== 429 || attempt >= retries || asked > maxWait) return null
  return Math.max(asked, Math.min(cap, base + backoffDelay(attempt, { base, cap }, random)))
}
