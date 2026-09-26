// Local-first autosave for one essay.
//
//  - Every change is written to a local draft (throttled to 400 ms) under
//    `naseeb-essay-draft:${userId}:${essayId}:${tabId}` as { doc, base_seq, updated_at }
//    (one queue per document tab).
//  - The server is synced 3 s after typing stops, at most every 20 s while
//    typing continues, and on blur / page hide / leaving (callers call flush/hide).
//  - One save in flight per essay; changes made meanwhile become one follow-up.
//  - Once the server has acknowledged a document, later saves send only the
//    changed top-level blocks (docDelta.js); a document identical to the
//    acknowledged one is not sent at all. A 409 "resync" (the server's copy
//    differs from that base) is answered with an immediate full save.
//  - A failed save is retried with the same client_save_id after a random
//    wait of up to 1, 2, 5, 10, 30 s (full jitter, so clients that failed
//    together don't retry together).
//  - 409 stops the queue until the caller resolves the conflict.
//  - 401 (session expired) stops syncing too: the text stays in the local draft
//    until the student signs in again; nothing is retried in a loop.
//
// Pure: time, timers, randomness, storage, ids and the network call are all
// injected, so it runs under plain `node` in tests.

import { diffDocs, prepareDoc } from './docDelta.js'
import { DRAFT_PREFIX } from './drafts.js'
import { fullJitter } from '../lib/backoff.js'

export const DEBOUNCE_MS = 3000
export const MAX_WAIT_MS = 20000
export const DRAFT_THROTTLE_MS = 400
export const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]
export const KEEPALIVE_LIMIT_BYTES = 60 * 1024

export { DRAFT_PREFIX, hasUserDrafts, removeUserDrafts } from './drafts.js'

// Drafts from before documents had tabs have no tab part (see sessions.js).
export const draftKey = (userId, essayId, tabId = null) => `${DRAFT_PREFIX}${userId}:${essayId}${tabId == null ? '' : `:${tabId}`}`

export function isQuotaError(error) {
  return Boolean(error) && (
    error.name === 'QuotaExceededError' || error.name === 'NS_ERROR_DOM_QUOTA_REACHED' || error.code === 22 || error.code === 1014
  )
}

// Writes a draft. When storage is full nothing else is evicted: every other
// draft is unsynced writing (a successful save removes it), so deleting one to
// make room would lose text. The caller shows the "storage full" notice and the
// server sync keeps working. -> { ok, quota }
export function writeDraft(storage, key, value) {
  try {
    storage.setItem(key, JSON.stringify(value))
    return { ok: true, quota: false }
  } catch (error) {
    return { ok: false, quota: isQuotaError(error) }
  }
}

export function readDraft(storage, key) {
  try {
    const raw = storage.getItem(key)
    if (!raw) return null
    const draft = JSON.parse(raw)
    if (!draft || typeof draft !== 'object' || !draft.doc || !Number.isInteger(draft.base_seq)) return null
    return draft
  } catch {
    return null
  }
}

export function removeDraft(storage, key) {
  try { storage.removeItem(key) } catch { /* ignore */ }
}

// Key order can differ after the server validates a doc, so compare canonically.
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]))
  }
  return value
}

export function sameDoc(a, b) {
  return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b))
}

// What to do with a local draft when an essay is opened. Decided by seq and
// content only: the device clock and the server clock can disagree, so a
// timestamp comparison could throw away unsynced text.
//  'none'    no draft
//  'discard' the draft matches the server copy
//  'push'    the draft builds on the server's current seq -> save it
//  'ask'     the server moved on since the draft was made -> ask the student
export function reconcileDraft(draft, server) {
  if (!draft) return 'none'
  if (server?.doc && sameDoc(server.doc, draft.doc)) return 'discard'
  return draft.base_seq === server?.save_seq ? 'push' : 'ask'
}

function isRetryable(error) {
  const status = error?.status
  return status == null || status === 0 || status === 408 || status === 429 || status >= 500
}

let idCounter = 0
function defaultId() {
  idCounter += 1
  const random = Math.random().toString(36).slice(2, 10)
  return `${Date.now().toString(36)}-${idCounter.toString(36)}-${random}`
}

export function createSaveQueue(options) {
  const {
    send,
    getSnapshot,
    storage,
    key,
    baseSeq = 0,
    now = () => Date.now(),
    setTimer = (fn, ms) => setTimeout(fn, ms),
    clearTimer = (id) => clearTimeout(id),
    makeId = defaultId,
    random = Math.random,
    // The server's document at `baseSeq`; deltas start from it. Without it the
    // first save sends the whole document.
    baseDoc = null,
    delta = true,
    isOnline = () => true,
    onStatus = () => {},
    onConflict = () => {},
    onSaved = () => {},
    onStorageWarning = () => {},
    onError = () => {},
  } = options

  let seq = baseSeq
  // The last document the server acknowledged at `seq` (prepareDoc output), or null.
  let base = delta && baseDoc ? prepareDoc(baseDoc) : null
  const prepared = new WeakMap() // payload -> prepareDoc output it was built from
  let dirty = false
  let firstDirtyAt = null
  let followUp = false
  let inFlight = null
  let pendingRetry = null
  let attempt = 0
  let conflict = null
  let expired = false
  let status = 'saved'
  let lastError = null
  let closed = false
  let forgotten = false
  let syncTimer = null
  let retryTimer = null
  let draftTimer = null
  let lastDraftAt = -Infinity
  let waiters = []

  const setStatus = (next) => {
    if (next === status) return
    status = next
    onStatus(next)
  }

  const clear = (timer) => { if (timer != null) clearTimer(timer); return null }

  function settleWaiters(error) {
    const list = waiters
    waiters = []
    for (const waiter of list) {
      if (error) waiter.reject(error)
      else waiter.resolve(seq)
    }
  }

  function writeDraftNow() {
    draftTimer = clear(draftTimer)
    if (!storage || !key || forgotten) return
    if (!dirty && !pendingRetry && !inFlight && !conflict && !expired) return
    lastDraftAt = now()
    const { doc } = getSnapshot()
    const result = writeDraft(storage, key, { doc, base_seq: seq, updated_at: new Date(now()).toISOString() })
    if (!result.ok) onStorageWarning(result)
  }

  function scheduleDraft() {
    if (draftTimer != null || closed) return
    const wait = Math.max(0, DRAFT_THROTTLE_MS - (now() - lastDraftAt))
    draftTimer = setTimer(writeDraftNow, wait)
  }

  function scheduleSync() {
    syncTimer = clear(syncTimer)
    if (closed || conflict || expired || !dirty) return
    const started = firstDirtyAt ?? now()
    const wait = Math.max(0, Math.min(DEBOUNCE_MS, started + MAX_WAIT_MS - now()))
    syncTimer = setTimer(() => { syncTimer = null; flush('timer') }, wait)
  }

  function sendPayload(payload, keepalive = false) {
    inFlight = payload
    setStatus('saving')
    const useKeepalive = keepalive && JSON.stringify(payload).length < KEEPALIVE_LIMIT_BYTES
    let request
    try {
      request = Promise.resolve(send(payload, { keepalive: useKeepalive }))
    } catch (error) {
      request = Promise.reject(error)
    }
    request.then((response) => succeeded(payload, response), (error) => failed(payload, error))
  }

  const retryDelay = (index) => fullJitter(BACKOFF_MS[Math.min(index, BACKOFF_MS.length - 1)], random)

  function succeeded(payload, response) {
    if (inFlight !== payload) return
    inFlight = null
    if (forgotten) { settleWaiters(null); return }
    attempt = 0
    lastError = null
    if (Number.isInteger(response?.save_seq)) seq = response.save_seq
    if (delta) {
      // An idempotent replay carries no hash; the save it replays sent this doc.
      const sentDoc = prepared.get(payload) || null
      base = sentDoc && (response?.doc_hash == null || response.doc_hash === sentDoc.hash) ? sentDoc : null
    }
    onSaved(response || {}, payload)
    settleClean()
  }

  // Nothing new was sent or everything sent has landed: settle or continue.
  function settleClean() {
    if (dirty) {
      writeDraftNow() // the unsent changes now build on the new seq
      setStatus('pending')
      if (followUp) { followUp = false; flush('follow-up') }
      else scheduleSync()
      return
    }
    followUp = false
    draftTimer = clear(draftTimer)
    if (storage && key && !forgotten) removeDraft(storage, key)
    setStatus('saved')
    settleWaiters(null)
  }

  function failed(payload, error) {
    if (inFlight !== payload) return
    inFlight = null
    // Signed out or tab deleted: a late answer (often a 404) changes nothing.
    if (forgotten) { settleWaiters(null); return }
    lastError = error
    const sentDoc = prepared.get(payload)
    if (error?.status === 409 && error.details?.code === 'resync' && sentDoc) {
      // The server's copy isn't our base: send the same text in full, right away.
      base = null
      const full = { doc: sentDoc.doc, base_seq: payload.base_seq, client_save_id: payload.client_save_id }
      if (payload.cursor != null) full.cursor = payload.cursor
      prepared.set(full, sentDoc)
      sendPayload(full)
      return
    }
    followUp = false
    if (error?.status === 409) {
      conflict = error.details || { code: 'conflict' }
      dirty = true
      syncTimer = clear(syncTimer)
      writeDraftNow()
      setStatus('conflict')
      onConflict(conflict)
      settleWaiters(error)
      return
    }
    if (error?.status === 401) {
      // Session over: keep the text on this device and wait for a new sign-in.
      expired = true
      dirty = true
      pendingRetry = null
      syncTimer = clear(syncTimer)
      retryTimer = clear(retryTimer)
      writeDraftNow()
      setStatus('expired')
      onError(error)
      settleWaiters(error)
      return
    }
    if (isRetryable(error)) {
      pendingRetry = payload
      const delay = retryDelay(attempt)
      attempt += 1
      retryTimer = clear(retryTimer)
      if (!closed) retryTimer = setTimer(() => { retryTimer = null; retryNow() }, delay)
      writeDraftNow()
      setStatus(error?.status === 0 || !isOnline() ? 'offline' : 'error')
    } else {
      // 400 invalid_doc, 413 doc_too_large, 403/404: retrying the same body won't help.
      dirty = true
      writeDraftNow()
      setStatus('error')
    }
    onError(error)
    settleWaiters(error)
  }

  function flush(reason = 'manual', { keepalive = false } = {}) {
    syncTimer = clear(syncTimer)
    if (forgotten || conflict || expired) return
    if (inFlight) { if (dirty) followUp = true; return }
    if (pendingRetry) {
      if (reason !== 'timer') retryNow({ keepalive })
      return
    }
    if (!dirty) return
    const snapshot = getSnapshot()
    const next = delta ? prepareDoc(snapshot.doc) : null
    dirty = false
    firstDirtyAt = null
    if (next && base && next.hash === base.hash) {
      // Typed and undone, or formatting toggled back: the server already has it.
      settleClean()
      return
    }
    const payload = { base_seq: seq, client_save_id: makeId() }
    if (next && base) {
      payload.ops = diffDocs(base, next)
      payload.doc_hash = next.hash
    } else {
      payload.doc = next ? next.doc : snapshot.doc
    }
    if (snapshot.cursor != null) payload.cursor = snapshot.cursor
    if (next) prepared.set(payload, next)
    sendPayload(payload, keepalive)
  }

  // The editor now shows `doc` as saved at `serverSeq` (undefined: unknown).
  function rebase(serverSeq, doc) {
    if (doc !== undefined) base = delta && doc ? prepareDoc(doc) : null
    else if (serverSeq !== seq) base = null
    seq = serverSeq
  }

  function retryNow({ keepalive = false } = {}) {
    retryTimer = clear(retryTimer)
    if (forgotten || conflict || inFlight) return
    if (expired) { expired = false; dirty = true } // explicit retry: try once more
    if (!pendingRetry) { flush('retry', { keepalive }); return }
    const payload = pendingRetry
    pendingRetry = null
    sendPayload(payload, keepalive)
  }

  const handle = {
    change() {
      if (closed) return
      dirty = true
      if (firstDirtyAt == null) firstDirtyAt = now()
      scheduleDraft()
      if (!inFlight && !pendingRetry) scheduleSync()
      if (status === 'saved') setStatus('pending')
    },
    flush,
    retryNow,
    // Page hidden or closing: write the draft now and try a keepalive save.
    hide() {
      if (dirty || pendingRetry || conflict) writeDraftNow()
      flush('hide', { keepalive: true })
    },
    // Resolves once everything is on the server (used before depth checks and restores).
    flushAndWait() {
      if (forgotten) return Promise.resolve(seq)
      if (conflict) return Promise.reject(Object.assign(new Error('conflict'), { status: 409, details: conflict }))
      if (expired) return Promise.reject(Object.assign(new Error('session expired'), { status: 401, details: null }))
      if (!dirty && !inFlight && !pendingRetry) return Promise.resolve(seq)
      const promise = new Promise((resolve, reject) => waiters.push({ resolve, reject }))
      if (!inFlight) flush('manual')
      else if (dirty) followUp = true
      return promise
    },
    // Conflict: re-save the local text against the server's new seq
    // (and its doc, when known, so the re-save can be a delta).
    keepMine(serverSeq, serverDoc) {
      if (forgotten) return
      conflict = null
      rebase(serverSeq, serverDoc)
      dirty = true
      firstDirtyAt = now()
      flush('keep-mine')
    },
    // The editor now shows the server version (load latest / restore / reload).
    acceptServer(serverSeq, serverDoc) {
      conflict = null
      expired = false
      rebase(serverSeq, serverDoc)
      dirty = false
      firstDirtyAt = null
      followUp = false
      pendingRetry = null
      attempt = 0
      syncTimer = clear(syncTimer)
      retryTimer = clear(retryTimer)
      draftTimer = clear(draftTimer)
      if (storage && key) removeDraft(storage, key)
      setStatus('saved')
      settleWaiters(null)
    },
    // Leaving the editor: save what is left, then stop scheduling timers.
    close() {
      if (dirty || pendingRetry) writeDraftNow()
      flush('leave')
      closed = true
      syncTimer = clear(syncTimer)
      retryTimer = clear(retryTimer)
      draftTimer = clear(draftTimer)
    },
    // Mounted again (React StrictMode re-runs effects): resume scheduling.
    reopen() {
      if (forgotten) return
      closed = false
      if (pendingRetry && retryTimer == null) retryTimer = setTimer(() => { retryTimer = null; retryNow() }, retryDelay(0))
      else if (dirty) scheduleSync()
    },
    // Before sign-out: a real save attempt. Resolves true when everything is
    // on the server, false when text is left only on this device.
    async syncBeforeLogout() {
      if (forgotten) return true
      if (dirty || pendingRetry || inFlight || conflict || expired) writeDraftNow()
      if (conflict || expired) return false
      if (!dirty && !inFlight && !pendingRetry) return true
      try {
        await handle.flushAndWait()
        return true
      } catch {
        return false
      }
    },
    // Logout: one last keepalive attempt, then never touch storage again.
    forget() {
      if (dirty || pendingRetry) flush('logout', { keepalive: true })
      forgotten = true
      closed = true
      syncTimer = clear(syncTimer)
      retryTimer = clear(retryTimer)
      draftTimer = clear(draftTimer)
    },
    // The tab was deleted on the server: nothing is left to save or keep.
    discard() {
      forgotten = true
      closed = true
      dirty = false
      firstDirtyAt = null
      followUp = false
      pendingRetry = null
      conflict = null
      expired = false
      syncTimer = clear(syncTimer)
      retryTimer = clear(retryTimer)
      draftTimer = clear(draftTimer)
      settleWaiters(null)
    },
    getState: () => ({ seq, dirty, status, inFlight: Boolean(inFlight), pendingRetry: Boolean(pendingRetry), conflict, expired, attempt, lastError, baseHash: base?.hash ?? null }),
  }
  return handle
}
