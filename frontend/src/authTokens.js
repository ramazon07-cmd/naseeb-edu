// Token storage and refresh coordination. Kept free of Vite/DOM globals so the
// logic can be unit-tested with plain Node.

export const TOKEN_KEYS = {
  access: 'naseeb-access-token',
  refresh: 'naseeb-refresh-token',
}

// Keys used before the AdmitFlow -> Naseeb rename. Tokens stored under them
// are moved once, so nobody is signed out by the rename.
export const LEGACY_TOKEN_KEYS = {
  access: 'admitflow-access-token',
  refresh: 'admitflow-refresh-token',
}

export function migrateLegacyTokens(storage, keys = TOKEN_KEYS, legacy = LEGACY_TOKEN_KEYS) {
  for (const name of Object.keys(keys)) {
    const old = storage.getItem(legacy[name])
    if (old === null) continue
    if (storage.getItem(keys[name]) === null) storage.setItem(keys[name], old)
    storage.removeItem(legacy[name])
  }
}

// `storage` may be a Storage or a function returning one (resolved lazily,
// because touching window.localStorage throws in some privacy modes).
export function createTokenStore(storage, keys = TOKEN_KEYS) {
  let migrated = false
  const resolve = () => {
    const target = typeof storage === 'function' ? storage() : storage
    if (!migrated && keys === TOKEN_KEYS) {
      migrated = true
      migrateLegacyTokens(target)
    }
    return target
  }
  return {
    get(key) {
      return resolve().getItem(keys[key])
    },
    save(tokens) {
      const target = resolve()
      if (tokens?.access) target.setItem(keys.access, tokens.access)
      if (tokens?.refresh) target.setItem(keys.refresh, tokens.refresh)
    },
    clear() {
      const target = resolve()
      target.removeItem(keys.access)
      target.removeItem(keys.refresh)
    },
  }
}

/**
 * Returns a `refresh(sentAccess)` function that shares one in-flight refresh
 * between every caller. With rotating, blacklisted refresh tokens a second
 * parallel refresh would send an already-used token and fail, so:
 *   - concurrent callers await the same promise;
 *   - a caller whose request carried an access token that has since been
 *     replaced simply reuses the new one;
 *   - a failed refresh only clears storage when the stored refresh token is
 *     still the one that was rejected (another tab may have rotated it).
 *
 * Across tabs (which share the stored tokens) the single flight is the
 * `lock(fn)` option, e.g. the Web Locks API: a tab that gets the lock after
 * another tab refreshed finds a new access token and reuses it. Without a lock
 * each tab first waits a random 0..`jitterMs`, then checks again, so tabs that
 * hit 401 together rarely spend the same refresh token.
 *
 * `send(refreshToken)` must resolve to `{ ok, status, payload }`.
 * `expired(status, payload)` builds the error thrown when the session is over;
 * `failed(status, payload)` the one for any other (e.g. 5xx) refresh failure,
 * which keeps the tokens so a later retry can still succeed.
 */
export function createRefresher({
  store, send, expired, failed = expired, lock = null, jitterMs = 0, random = Math.random,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  let inflight = null

  async function run() {
    const sent = store.get('refresh')
    if (!sent) throw expired(401, null)
    const { ok, status, payload } = await send(sent)
    if (ok && payload?.access) {
      store.save(payload)
      return payload.access
    }
    const current = store.get('refresh')
    if (current && current !== sent) {
      // Someone else rotated the pair while we were waiting; use theirs.
      return store.get('access')
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
