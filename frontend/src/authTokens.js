// Session state and refresh coordination. Kept free of Vite/DOM globals so the
// logic can be unit-tested with plain Node.
//
// The refresh token is an HttpOnly cookie the backend sets on sign-in and
// refresh: script never sees it. The access token lives only in memory, so a
// reload or a new tab gets one from the cookie (or from another tab, see
// createRefresher). localStorage only holds SESSION_HINT_KEY, a non-secret
// refresh generation: a counter bumped on every sign-in and refresh. Its
// presence tells a fresh page a silent refresh is worth trying, a change tells
// a tab that another tab rotated the cookie, and its removal is the cross-tab
// sign-out signal (a storage event in every other tab).

export const SESSION_HINT_KEY = 'naseeb-session'

// Tabs hand each other fresh access tokens here (same origin only, never stored).
export const AUTH_CHANNEL = 'naseeb-auth'

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
  const generation = () => {
    try { return resolve()?.getItem(SESSION_HINT_KEY) ?? null } catch { return null }
  }
  return {
    get(key) {
      return key === 'access' ? access : null
    },
    // A new token from the server: this tab rotated the cookie (or signed in).
    save(tokens) {
      if (!tokens?.access) return
      access = tokens.access
      try { resolve()?.setItem(SESSION_HINT_KEY, String((Number(generation()) || 0) + 1)) } catch { /* storage full or blocked */ }
    },
    // A token another tab got: no rotation happened here. Ignored once signed out.
    adopt(token) {
      if (token && generation() !== null) access = token
    },
    clear() {
      access = null
      try { resolve()?.removeItem(SESSION_HINT_KEY) } catch { /* storage blocked */ }
    },
    generation,
    // An access token in memory, or a cookie session to restore from.
    hasSession() {
      return Boolean(access) || generation() !== null
    },
  }
}

// A storage event meaning another tab signed out (or storage was cleared).
export function isSignOutSignal(event) {
  return (event.key === SESSION_HINT_KEY || event.key === null) && event.newValue === null
}

/**
 * Returns a `refresh(sentAccess)` function that shares one in-flight refresh
 * between every caller. Refresh tokens rotate and are blacklisted after use,
 * and every tab sends the same cookie, so:
 *   - concurrent callers in this tab await the same promise;
 *   - a caller whose request carried an access token that has since been
 *     replaced (here, or adopted from another tab) reuses the new one;
 *   - across tabs, `lock(fn)` (the Web Locks API) runs one refresh at a time.
 *     The winner `share()`s its access token; a tab that waited behind it
 *     sees the generation move, gives the token a moment to arrive and
 *     reuses it instead of rotating again;
 *   - without a lock (plain-http LAN, older Safari) tabs wait a random
 *     0..`jitterMs`, and a tab that loses the race (its cookie was rotated by
 *     another tab mid-flight, so the server says 401) checks the generation:
 *     if another tab refreshed it reuses that token or retries once with the
 *     new cookie. Only when nobody refreshed is the session over.
 *
 * `send()` must resolve to `{ ok, status, payload }` (the cookie goes along).
 * 400/401/403 end the session: `store.clear()` and throw `expired(401, payload)`
 * (403 means the request failed the CSRF/Origin check, which a retry cannot
 * fix, so `warn` reports it). Any other failure (5xx, offline) throws
 * `failed(status, payload)` and keeps the session for a later retry.
 */
export function createRefresher({
  store, send, expired, failed = expired, lock = null, jitterMs = 0, random = Math.random,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  share = () => {}, settleMs = 400, handoffMs = 60, warn = () => {},
}) {
  let inflight = null

  async function attempt() {
    const before = store.generation()
    const result = await send()
    if (result.ok && result.payload?.access) {
      store.save(result.payload)
      share(result.payload.access)
      return { access: result.payload.access }
    }
    return { result, before }
  }

  async function run(baseline) {
    const first = await attempt()
    if (first.access) return first.access
    let { result } = first
    if (![400, 401, 403].includes(result.status)) throw failed(result.status || 0, result.payload)
    // Did another tab rotate the cookie while ours was in flight? Its response
    // can land a moment after our 401, so look again before giving up.
    let rotated = store.generation() !== first.before
    if (!rotated && store.generation() !== null) {
      await sleep(settleMs)
      rotated = store.generation() !== first.before
    }
    if (rotated) {
      // The winner's token may still be on its way over the channel.
      const adopted = newer(baseline) || (await sleep(handoffMs), newer(baseline))
      if (adopted) return adopted
      const second = await attempt()
      if (second.access) return second.access
      result = second.result
    }
    if (result.status === 403) warn('Session refresh was rejected (403): check CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS.', result.payload)
    store.clear()
    throw expired(401, result.payload)
  }

  // A token newer than the one this caller started with: someone refreshed already.
  const newer = (baseline) => {
    const stored = store.get('access')
    return stored && stored !== baseline ? stored : null
  }

  async function underLock(baseline, generation) {
    const reused = newer(baseline)
    if (reused) return reused
    if (store.generation() !== generation && store.generation() !== null) {
      // Another tab refreshed while we waited for the lock: its token is on the way.
      await sleep(handoffMs)
      const handed = newer(baseline)
      if (handed) return handed
    }
    return run(baseline)
  }

  async function coordinated(baseline) {
    const generation = store.generation()
    if (lock) return lock(() => underLock(baseline, generation))
    if (jitterMs > 0) await sleep(Math.floor(random() * jitterMs))
    return newer(baseline) || run(baseline)
  }

  return function refresh(sentAccess) {
    const baseline = sentAccess !== undefined ? sentAccess : store.get('access')
    const stored = newer(baseline)
    if (stored) return Promise.resolve(stored)
    if (!inflight) inflight = coordinated(baseline).finally(() => { inflight = null })
    return inflight
  }
}

// Web Locks when the browser has them (shared by every tab of this origin).
export function browserLock(name) {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : null
  return locks?.request ? (fn) => locks.request(name, fn) : null
}

async function readPayload(response) {
  const text = await response.text()
  if (!text) return null
  try { return JSON.parse(text) } catch { return text }
}

/**
 * The two cookie-authenticated calls. `request(url, options)` is fetch (or a
 * wrapper with the same contract). Both send the cookie (`credentials`, so a
 * same-site API on another origin works too) and the X-Requested-With header
 * the backend requires as CSRF protection; neither has a body.
 *
 * logout() blacklists the refresh token and clears the cookie, retrying once.
 * Sign-in must wait for it (`settled()`): a logout response that lands after a
 * new sign-in would delete the new cookie.
 */
export function createCookieAuth({ apiUrl, request, logoutTimeoutMs = 4000 }) {
  const post = (path, extra = {}) => request(`${apiUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    ...extra,
  })
  let pendingLogout = null

  const logoutOnce = async () => {
    const response = await post('/auth/logout/', { keepalive: true, timeoutMs: logoutTimeoutMs })
    if (!response.ok) throw new Error(`logout failed: ${response.status}`)
  }

  return {
    async refresh() {
      const response = await post('/auth/token/refresh/')
      return { ok: response.ok, status: response.status, payload: await readPayload(response) }
    },
    // Resolves true once the server ended the session, false if both tries failed.
    logout() {
      if (!pendingLogout) {
        pendingLogout = logoutOnce()
          .catch(logoutOnce)
          .then(() => true, () => false)
          .finally(() => { pendingLogout = null })
      }
      return pendingLogout
    },
    settled() {
      return pendingLogout || Promise.resolve(true)
    },
  }
}
