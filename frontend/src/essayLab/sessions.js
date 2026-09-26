// One save session per open document tab.
//
// A document's tabs each keep their own save queue (own save_seq, own local
// draft) for as long as the document is open, so switching tabs never waits
// for a save and never loses a pending one: the tab you left keeps syncing in
// the background while only the open tab has an editor.
//
// Framework-free apart from the injected send(); the editor attaches itself
// with session.attach(editor) and detaches when the tab is switched.

import { repairDoc } from './docDelta.js'
import { createSaveQueue, draftKey, readDraft, reconcileDraft, removeDraft, writeDraft } from './saveQueue.js'

export function createTabSession({ essayId, tab, userId, storage, send, adoptLegacyDraft = false, isOnline = () => true, onSaved = () => {} }) {
  const key = draftKey(userId ?? 'me', essayId, tab.id)
  let draft = storage ? readDraft(storage, key) : null
  if (adoptLegacyDraft && storage) {
    // A draft written before documents had tabs moves to this tab. When the
    // tab already has its own draft, that one was written later and wins.
    const legacyKey = draftKey(userId ?? 'me', essayId)
    const legacy = draft ? null : readDraft(storage, legacyKey)
    if (legacy) draft = legacy
    if (!legacy || writeDraft(storage, key, legacy).ok) removeDraft(storage, legacyKey)
  }
  const decision = reconcileDraft(draft, tab)
  if (decision === 'discard') removeDraft(storage, key)

  const listeners = new Set()
  const session = {
    id: tab.id,
    key,
    storage,
    decision,
    // The latest text while no editor shows this tab.
    doc: decision === 'push' ? draft.doc : tab.doc,
    cursor: tab.last_cursor ?? null,
    editor: null,
    state: {
      status: 'saved',
      savedAt: tab.last_edited_at,
      error: null,
      conflict: null,
      storageWarning: false,
      // An unsynced draft from this device built on an older version: the student chooses.
      unsynced: decision === 'ask' ? draft : null,
    },
    set(patch) {
      session.state = { ...session.state, ...patch }
      for (const listener of listeners) listener()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    snapshot() {
      const { editor } = session
      if (editor && !editor.isDestroyed) return { doc: repairDoc(editor.getJSON()), cursor: editor.state.selection.head }
      return { doc: session.doc, cursor: session.cursor }
    },
    attach(editor) {
      session.editor = editor
    },
    // The editor goes away (another tab opened): keep its text and sync now.
    detach(editor) {
      if (session.editor !== editor) return
      if (!editor.isDestroyed) {
        session.doc = repairDoc(editor.getJSON())
        session.cursor = editor.state.selection.head
      }
      session.editor = null
      if (!session.disposed) session.queue.flush('switch')
    },
    // The server stored new text for this tab (a save or a restore): update
    // "Saved …" and the tab's and the document's counts.
    applySaved(response) {
      session.set({ savedAt: response.saved_at || new Date().toISOString() })
      onSaved(tab.id, response)
    },
    // The tab was deleted: nothing more to save, no draft to keep.
    dispose() {
      session.disposed = true
      session.queue.discard()
      removeDraft(storage, key)
    },
  }

  session.queue = createSaveQueue({
    send: (payload, options) => send({ ...payload, tab: tab.id }, options),
    getSnapshot: session.snapshot,
    storage,
    key,
    baseSeq: tab.save_seq ?? 0,
    baseDoc: tab.doc,
    isOnline,
    onStatus: (status) => session.set(status === 'saved' || status === 'saving' ? { status, error: null } : { status }),
    onSaved: (response) => session.applySaved(response),
    onConflict: (details) => session.set({ conflict: details || {} }),
    onStorageWarning: () => session.set({ storageWarning: true }),
    onError: (error) => session.set({ error }),
  })

  // A newer local draft based on the server's seq is sent right away.
  if (decision === 'push') {
    session.queue.change()
    session.queue.flush('load')
  }
  return session
}

// The student picked a version of an unsynced draft.
export function keepLocalDraft(session) {
  const draft = session.state.unsynced
  if (!draft) return null
  session.doc = draft.doc
  session.set({ unsynced: null })
  session.queue.keepMine(session.queue.getState().seq)
  return draft.doc
}

export function discardLocalDraft(session) {
  removeDraft(session.storage, session.key)
  session.set({ unsynced: null })
}

// The save sessions of one open document, by tab id. A draft from before tabs
// is offered only to the first tab opened in this visit, never to tabs opened
// or created later.
//
// subscribe()/version() follow useSyncExternalStore: the version changes
// whenever any tab's save state does, so the header can show every tab's.
export function createSessionRegistry(create) {
  const sessions = new Map()
  const unsubscribe = new Map()
  const listeners = new Set()
  let legacyClaimed = false
  let version = 0
  const changed = () => {
    version += 1
    for (const listener of listeners) listener()
  }
  return {
    get: (id) => sessions.get(id),
    has: (id) => sessions.has(id),
    all: () => [...sessions.values()],
    open(tab) {
      const existing = sessions.get(tab.id)
      if (existing) return existing
      const session = create(tab, { adoptLegacyDraft: !legacyClaimed })
      legacyClaimed = true
      sessions.set(tab.id, session)
      if (session.subscribe) unsubscribe.set(tab.id, session.subscribe(changed))
      changed()
      return session
    },
    // The tab was deleted: stop its saves and forget it.
    remove(id) {
      if (!sessions.has(id)) return
      unsubscribe.get(id)?.()
      unsubscribe.delete(id)
      sessions.get(id).dispose()
      sessions.delete(id)
      changed()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    version: () => version,
  }
}

// Why a tab's text is not on the server, when it will not get there by itself
// soon: 'conflict', 'rejected' (a 4xx the same body can't fix), 'expired',
// 'error' (retrying). Null when it is saved or on its way.
export function saveProblem(state) {
  if (!state) return null
  if (state.conflict || state.status === 'conflict') return 'conflict'
  if (state.status === 'expired') return 'expired'
  if (state.status !== 'error') return null
  const code = state.error?.status
  return code >= 400 && code < 500 && code !== 408 && code !== 429 ? 'rejected' : 'error'
}

const PROBLEM_RANK = { conflict: 4, rejected: 3, expired: 2, error: 1 }

// Tabs that are not saved, worst first: [{ id, problem }].
export function unsavedTabs(sessions) {
  return sessions.map((session) => ({ id: session.id, problem: saveProblem(session.state) }))
    .filter((item) => item.problem)
    .sort((a, b) => PROBLEM_RANK[b.problem] - PROBLEM_RANK[a.problem])
}

// Saves every tab now (leaving the document). Resolves with the ids of the
// tabs whose text is only in this device's drafts, after at most `timeoutMs`.
export async function syncTabs(sessions, { timeoutMs = 8000, setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
  let timer
  const timeout = new Promise((resolve) => { timer = setTimer(() => resolve(false), timeoutMs) })
  try {
    const results = await Promise.all(sessions.map((session) => Promise.race([
      Promise.resolve().then(() => session.queue.syncBeforeLogout()).catch(() => false),
      timeout,
    ])))
    return sessions.filter((_, index) => !results[index]).map((session) => session.id)
  } finally {
    clearTimer(timer)
  }
}
