// Session state and refresh coordination. Kept free of Vite/DOM globals so the
// logic can be unit-tested with plain Node.
//
// The refresh token is an HttpOnly cookie the backend sets on sign-in and
// refresh: script never sees it. The access token lives only in memory, so a
// reload or a new tab gets one from the cookie (or from another tab, see
// createRefresher). localStorage only holds SESSION_HINT_KEY, which holds no
// secret: "<sign-in id>.<refresh count>". The sign-in id changes on every
// sign-in, the count on every refresh.
//   - present: a fresh page tries a silent refresh;
//   - changed: another tab rotated the cookie (or signed in again);
//   - removed: the cross-tab sign-out signal (a storage event in every tab).
import { readPayload } from './lib/payload.js'
import { SESSION_HINT_KEY } from './sessionKeys.js'
import { safeStorage } from './userStorage.js'

export { SESSION_HINT_KEY }

// Tabs hand each other fresh access tokens here (same origin only, never stored).
export const AUTH_CHANNEL = 'naseeb-auth'

// One lock for everything that changes the cookie: refresh, sign-in, sign-out.
export const AUTH_LOCK = 'naseeb-token-refresh'

// Where tokens were stored before they moved to the cookie (and before the
// AdmitFlow -> Naseeb rename).
export const STALE_TOKEN_KEYS = {
  'naseeb-access-token': 'access',
  'naseeb-refresh-token': 'refresh',
  'admitflow-access-token': 'access',
  'admitflow-refresh-token': 'refresh',
}

/**
 * One-time migration from the previous frontend: every refresh token it left in
 * localStorage is sent to `revoke(token)` (the server blacklists it), then all
 * stale keys are removed, whether or not the server could be reached. Those
 * users sign in once more.
 */
export async function migrateLegacyTokens(storage, revoke) {
  const target = safeStorage(storage)
  if (!target) return
  const read = (key) => { try { return target.getItem(key) } catch { return null } }
  const refreshTokens = [...new Set(Object.entries(STALE_TOKEN_KEYS)
    .filter(([, kind]) => kind === 'refresh').map(([key]) => read(key)).filter(Boolean))]
  for (const token of refreshTokens) {
    try { await revoke(token) } catch { /* offline: the token still expires on its own */ }
  }
  for (const key of Object.keys(STALE_TOKEN_KEYS)) {
    try { target.removeItem(key) } catch { /* storage unavailable */ }
  }
}

function newSignInId(random = Math.random) {
  return Math.floor(random() * 36 ** 8).toString(36)
}

// `storage` may be a Storage or a function returning one (resolved lazily,
// because touching window.localStorage throws in some privacy modes; the
// session then simply does not survive a reload).
export function createSessionStore(storage, { random = Math.random } = {}) {
  let access = null
  // Bumped when this tab signs out: a refresh that lands afterwards is dropped.
  let epoch = 0
  // This tab signed out and is waiting for the server; the counter stays until then.
  let endedHere = false
  const read = () => { try { return safeStorage(storage)?.getItem(SESSION_HINT_KEY) ?? null } catch { return null } }
  const write = (value) => { try { safeStorage(storage)?.setItem(SESSION_HINT_KEY, value) } catch { /* full or blocked */ } }
  const remove = () => { try { safeStorage(storage)?.removeItem(SESSION_HINT_KEY) } catch { /* blocked */ } }
  const signInIdOf = (value) => (value === null ? null : value.split('.')[0])
  return {
    get(key) {
      return key === 'access' ? access : null
    },
    // A new token from the server. `signIn`: a new sign-in (new session id on
    // the server), otherwise a refresh of the current one.
    save(tokens, { signIn = false } = {}) {
      if (!tokens?.access) return
      const current = read()
      const [id, count] = current && !signIn ? current.split('.') : [newSignInId(random), '0']
      access = tokens.access
      endedHere = false
      write(`${id}.${(Number(count) || 0) + (signIn ? 0 : 1)}`)
    },
    // A token another tab got: no rotation happened here.
    adopt(token) {
      if (token && !endedHere && read() !== null) access = token
    },
    // Signing out: forget the token and drop any refresh still in flight. The
    // other tabs keep going until clear() removes the counter.
    endHere() {
      epoch += 1
      access = null
      endedHere = true
      return signInIdOf(read())
    },
    // Ends the session for every tab, unless `signInId` is given and a newer
    // sign-in (from another tab) has replaced it since.
    clear(signInId) {
      access = null
      if (signInId === undefined || signInIdOf(read()) === signInId) remove()
    },
    epoch: () => epoch,
    generation: read,
    signInId: () => signInIdOf(read()),
    // An access token in memory, or a cookie session to restore from.
    hasSession() {
      return !endedHere && (Boolean(access) || read() !== null)
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
 *     new cookie. Only when nobody refreshed is the session over;
 *   - a refresh that lands after this tab signed out (store.endHere()) is
 *     dropped: no token, no counter. (The server revokes the whole chain on
 *     logout, so the cookie it set is dead too.)
 *
 * `send()` must resolve to `{ ok, status, payload }` (the cookie goes along).
 * 400/401/403 end the session: `store.clear()` and throw `expired(401, payload)`
 * (403 means the request failed the CSRF/Origin check, which a retry cannot
 * fix, so `warn` reports it). Any other failure (5xx, offline) throws
 * `failed(status, payload)` and keeps the session for a later retry.
 *
 * `refresh.settled()` resolves once no refresh of this tab is in flight.
 */
export function createRefresher({
  store, send, expired, failed = expired, lock = null, jitterMs = 0, random = Math.random,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  share = () => {}, settleMs = 400, handoffMs = 60, warn = () => {},
}) {
  let inflight = null

  async function attempt(epoch) {
    const before = store.generation()
    const result = await send()
    if (store.epoch() !== epoch) throw expired(401, null)
    if (result.ok && result.payload?.access) {
      store.save(result.payload)
      share(result.payload.access)
      return { access: result.payload.access }
    }
    return { result, before }
  }

  async function run(baseline, epoch) {
    if (store.epoch() !== epoch) throw expired(401, null)
    const first = await attempt(epoch)
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
    if (rotated && store.epoch() === epoch) {
      // The winner's token may still be on its way over the channel.
      const adopted = newer(baseline) || (await sleep(handoffMs), newer(baseline))
      if (adopted) return adopted
      const second = await attempt(epoch)
      if (second.access) return second.access
      result = second.result
    }
    if (store.epoch() !== epoch) throw expired(401, null)
    if (result.status === 403) warn('Session refresh was rejected (403): check CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS.', result.payload)
    store.clear()
    throw expired(401, result.payload)
  }

  // A token newer than the one this caller started with: someone refreshed already.
  const newer = (baseline) => {
    const stored = store.get('access')
    return stored && stored !== baseline ? stored : null
  }

  async function underLock(baseline, generation, epoch) {
    const reused = newer(baseline)
    if (reused) return reused
    if (store.generation() !== generation && store.generation() !== null) {
      // Another tab refreshed while we waited for the lock: its token is on the way.
      await sleep(handoffMs)
      const handed = newer(baseline)
      if (handed) return handed
    }
    return run(baseline, epoch)
  }

  async function coordinated(baseline, epoch) {
    const generation = store.generation()
    if (lock) return lock(() => underLock(baseline, generation, epoch))
    if (jitterMs > 0) await sleep(Math.floor(random() * jitterMs))
    return newer(baseline) || run(baseline, epoch)
  }

  function refresh(sentAccess) {
    const baseline = sentAccess !== undefined ? sentAccess : store.get('access')
    const stored = newer(baseline)
    if (stored) return Promise.resolve(stored)
    if (!inflight) inflight = coordinated(baseline, store.epoch()).finally(() => { inflight = null })
    return inflight
  }
  refresh.settled = () => (inflight ? inflight.then(() => {}, () => {}) : Promise.resolve())
  return refresh
}

// Web Locks when the browser has them (shared by every tab of this origin).
export function browserLock(name) {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : null
  return locks?.request ? (fn) => locks.request(name, fn) : null
}

/**
 * The cookie-authenticated calls and sign-out. `request(url, options)` is
 * fetch (or a wrapper with the same contract). Every call sends the cookie
 * (`credentials`, so a same-site API on another origin works too) and the
 * X-Requested-With header the backend requires as CSRF protection.
 *
 * Sign-in and sign-out run under `lock` (shared with the refresher), so across
 * tabs they never overlap a refresh or each other: a sign-out never goes out
 * with a cookie that a refresh is about to replace, and its response (which
 * deletes the cookie) can never land after a newer sign-in set one.
 */
export function createCookieAuth({ apiUrl, request, store, settleRefreshes = async () => {}, lock = null, logoutTimeoutMs = 4000 }) {
  const post = (path, extra = {}) => request(`${apiUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    ...extra,
    headers: { 'X-Requested-With': 'XMLHttpRequest', ...extra.headers },
  })
  const locked = (fn) => (lock ? lock(fn) : fn())
  let pendingLogout = null

  const logoutOnce = async () => {
    const response = await post('/auth/logout/', { timeoutMs: logoutTimeoutMs })
    if (!response.ok) throw new Error(`logout failed: ${response.status}`)
  }

  // The server side of sign-out for the session `signInId`: skipped when a
  // newer sign-in (another tab) replaced it, since the cookie is then that
  // one's. Resolves true when the session is over on the server.
  // This tab's refresh is awaited before taking the lock (it may be queued on
  // it); after store.endHere() it is dropped without sending.
  const endOnServer = async (signInId) => {
    await settleRefreshes()
    return locked(async () => {
      if (store && signInId !== undefined && store.signInId() !== null && store.signInId() !== signInId) return true
      try {
        await logoutOnce()
      } catch {
        try { await logoutOnce() } catch { return false }
      }
      return true
    })
  }

  return {
    async refresh() {
      const response = await post('/auth/token/refresh/')
      return { ok: response.ok, status: response.status, payload: await readPayload(response) }
    },
    // Signs out on the server, retrying once. `signInId` is the session being
    // ended (store.endHere()'s result). Concurrent calls share one attempt.
    logout(signInId) {
      if (!pendingLogout) pendingLogout = endOnServer(signInId).finally(() => { pendingLogout = null })
      return pendingLogout
    },
    // Runs a sign-in after any sign-out of this tab, under the lock.
    async signIn(fn) {
      await pendingLogout
      return locked(fn)
    },
    // Blacklists a refresh token the previous frontend kept in localStorage.
    async revokeLegacy(token) {
      const response = await post('/auth/logout/', {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: token }),
        timeoutMs: logoutTimeoutMs,
      })
      if (!response.ok) throw new Error(`legacy revoke failed: ${response.status}`)
    },
  }
}
