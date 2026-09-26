// Account-level draft bookkeeping, used at sign-out by api.js. Kept apart
// from saveQueue.js so the main bundle doesn't carry the editor's save code.

export const DRAFT_PREFIX = 'naseeb-essay-draft:'

function storageKeys(storage) {
  const keys = []
  try {
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i)
      if (key != null) keys.push(key)
    }
  } catch { /* storage unavailable */ }
  return keys
}

// Drafts only exist while text is not on the server (a successful save removes
// them), so any left for this user means unsynced writing on this device.
export function hasUserDrafts(storage, userId) {
  const prefix = `${DRAFT_PREFIX}${userId}:`
  return storageKeys(storage).some((key) => key.startsWith(prefix))
}

// Sign-out: remove one account's drafts, never another account's.
export function removeUserDrafts(storage, userId) {
  const prefix = `${DRAFT_PREFIX}${userId}:`
  let removed = 0
  for (const key of storageKeys(storage)) {
    if (key.startsWith(prefix)) {
      try { storage.removeItem(key); removed += 1 } catch { /* ignore */ }
    }
  }
  return removed
}
