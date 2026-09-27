// Profile Assessment results that are finished on this device but not yet
// confirmed by the server. Each entry is the exact payload to POST; its
// completed_at makes a repeated POST return the stored row instead of adding a
// second attempt, so retrying is always safe.
import { backoffDelay } from './backoff.js'

export const SAVE_RETRY = { base: 2000, cap: 60000 }

export function loadPendingAttempts(storage, key) {
  try {
    const value = JSON.parse(storage?.getItem(key) || '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return Object.fromEntries(Object.entries(value).filter(([challenge, payload]) =>
      payload && typeof payload === 'object' && payload.challenge === challenge
      && payload.answers && typeof payload.answers === 'object' && typeof payload.completed_at === 'string'))
  } catch { return {} }
}

export function storePendingAttempts(storage, key, pending) {
  try {
    if (Object.keys(pending).length) storage?.setItem(key, JSON.stringify(pending))
    else storage?.removeItem(key)
  } catch { /* private mode: the retry still runs while the page is open */ }
}

// No connection (0), timeout, rate limit or a server error: worth another try.
// Anything else (400, 403, ...) will fail the same way again.
export function isRetryableSaveError(error) {
  const status = error?.status
  if (status === undefined || status === null) return error?.name !== 'AbortError'
  return status === 0 || status === 408 || status === 429 || status >= 500
}

export function saveRetryDelay(attempt, random = Math.random) {
  // Never retry immediately: at least a second, even when jitter rolls low.
  return Math.max(1000, backoffDelay(attempt, SAVE_RETRY, random))
}

// Server answers win, except for a challenge whose newer result is still
// waiting to be saved: its answers on this device are the newer ones.
export function mergeServerAnswers(local, latestByChallenge, pending) {
  const merged = { ...local }
  for (const row of Object.values(latestByChallenge)) {
    if (pending[row.challenge]) continue
    Object.assign(merged, row.answers)
  }
  return merged
}

// Recommendations are built from what the account holds, so they unlock only
// once every challenge is saved there and nothing newer is still waiting.
export function assessmentLockReason({ challengeKeys, completedKeys, saved, pending, loading, loadFailed }) {
  if (!challengeKeys.every((key) => completedKeys.includes(key))) return 'incomplete'
  if (loading) return 'loading'
  if (Object.keys(pending).length) return 'pending'
  if (loadFailed || !challengeKeys.every((key) => saved[key])) return 'unsynced'
  return null
}
