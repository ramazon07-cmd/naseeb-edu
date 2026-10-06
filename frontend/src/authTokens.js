// Session state and refresh coordination. Kept free of Vite/DOM globals so the
// logic can be unit-tested with plain Node.
//
// The refresh token is an HttpOnly cookie the backend sets on sign-in and
// refresh: script never sees it. The access token lives only in memory, so a
// reload or a new tab gets a fresh one from the cookie. localStorage only holds
// SESSION_HINT_KEY, a non-secret "this browser is signed in" flag: it tells a
// fresh page whether a silent refresh is worth trying, and its removal is the
// cross-tab sign-out signal (a storage event in every other tab).

export const SESSION_HINT_KEY = 'naseeb-session'

// Where tokens were stored before they moved to the cookie (and before the
// AdmitFlow -> Naseeb rename). Removed on first load; those users sign in once.
export const STALE_TOKEN_KEYS = [
  'naseeb-access-token',
  'naseeb-refresh-token',
  'admitflow-access-token',
  'admitflow-refresh-token',
]

export function dropStoredTokens(storage) {
  for (const key of STALE_TOKEN_KEYS) storage.removeItem(key)
}

// `storage` may be a Storage or a function returning one (resolved lazily,
// because touching window.localStorage throws in some privacy modes; the
// session then simply does not survive a reload).
export function createSessionStore(storage) {
  let access = null
  let migrated = false
  const resolve = () => {
    try {
      const target = typeof storage === 'function' ? storage() : storage
      if (!migrated) {
        migrated = true
        dropStoredTokens(target)
      }
      return target
    } catch {
      return null
    }
  }
  const hinted = () => {
    try { return resolve()?.getItem(SESSION_HINT_KEY) === '1' } catch { return false }
  }
  return {
    get(key) {
      return key === 'access' ? access : null
    },
    save(tokens) {
      if (!tokens?.access) return
      access = tokens.access
      try { resolve()?.setItem(SESSION_HINT_KEY, '1') } catch { /* storage full or blocked */ }
    },
    clear() {
      access = null
      try { resolve()?.removeItem(SESSION_HINT_KEY) } catch { /* storage blocked */ }
    },
    // An access token in memory, or a cookie session to restore from.
    hasSession() {
      return Boolean(access) || hinted()
    },
  }
}

// A storage event meaning another tab signed out (or storage was cleared).
export function isSignOutSignal(event) {
  return (event.key === SESSION_HINT_KEY || event.key === null) && event.newValue === null
}

/**
 * Returns a `refresh(sentAccess)` function that shares one in-flight refresh
 * between every caller. With rotating, blacklisted refresh tokens a second
 * parallel refresh would send an already-used cookie and fail, so:
 *   - concurrent callers in this tab await the same promise;
 *   - a caller whose request carried an access token that has since been
 *     replaced simply reuses the new one.
 *
 * Tabs share the cookie but not the access token, so across tabs the single
 * flight is the `lock(fn)` option, e.g. the Web Locks API: a tab that gets the
 * lock after another tab refreshed sends the rotated cookie. Without a lock
 * each tab first waits a random 0..`jitterMs`.
 *
 * `send()` must resolve to `{ ok, status, payload }` (the cookie goes along).
 * `expired(status, payload)` builds the error thrown when the session is over
 * (400/401: the store is cleared); `failed(status, payload)` the one for any
 * other refresh failure (5xx, offline), which keeps the session for a retry.
 */
export function createRefresher({
  store, send, expired, failed = expired, lock = null, jitterMs = 0, random = Math.random,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  let inflight = null

  async function run() {
    const { ok, status, payload } = await send()
    if (ok && payload?.access) {
      store.save(payload)
      return payload.access
    }
    if (status === 400 || status === 401) {
      store.clear()
      throw expired(401, payload)
    }
    throw failed(status || 0, payload)
  }

  // A newer access token than the one the failed request carried: someone refreshed already.
  const newer = (sentAccess) => {
    const stored = store.get('access')
    return sentAccess !== undefined && stored && stored !== sentAccess ? stored : null
  }

  async function coordinated(sentAccess) {
    if (lock) return lock(() => newer(sentAccess) || run())
    if (jitterMs > 0) await sleep(Math.floor(random() * jitterMs))
    return newer(sentAccess) || run()
  }

  return function refresh(sentAccess) {
    const stored = newer(sentAccess)
    if (stored) return Promise.resolve(stored)
    if (!inflight) inflight = coordinated(sentAccess).finally(() => { inflight = null })
    return inflight
  }
}

// Web Locks when the browser has them (shared by every tab of this origin).
export function browserLock(name) {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : null
  return locks?.request ? (fn) => locks.request(name, fn) : null
}
