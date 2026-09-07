export function accountStorageKey(baseKey, userId) {
  return userId === undefined || userId === null || userId === ''
    ? null
    : `${baseKey}:user:${encodeURIComponent(String(userId))}`
}

export function readAccountStorage(baseKey, userId, fallback) {
  const key = accountStorageKey(baseKey, userId)
  try {
    // The old shared value has no trustworthy owner and must never be migrated.
    globalThis.localStorage.removeItem(baseKey)
    return key ? JSON.parse(globalThis.localStorage.getItem(key) || 'null') ?? fallback : fallback
  } catch { return fallback }
}

export function writeAccountStorage(baseKey, userId, value) {
  const key = accountStorageKey(baseKey, userId)
  if (!key) return
  try {
    if (value === null) globalThis.localStorage.removeItem(key)
    else globalThis.localStorage.setItem(key, JSON.stringify(value))
  } catch { /* The caller keeps its in-memory copy when storage is unavailable. */ }
}

// One queue per account survives page changes and component remounts. An old
// request can only acknowledge this exact account's queue, including new entries
// added while that request was pending.
const screenTimeQueues = new Map()

export function getScreenTimeQueue(baseKey, userId) {
  const key = accountStorageKey(baseKey, userId)
  if (!key) return null
  if (screenTimeQueues.has(key)) return screenTimeQueues.get(key)
  const stored = readAccountStorage(baseKey, userId, [])
  let entries = Array.isArray(stored) ? stored.filter((entry) => (
    entry && /^\d{4}-\d{2}-\d{2}$/.test(entry.date) && typeof entry.page === 'string'
    && Number.isFinite(entry.seconds) && entry.seconds > 0
  )) : []
  let sending = false
  const persist = () => writeAccountStorage(baseKey, userId, entries.length ? entries : null)
  const queue = {
    add(date, page, seconds) {
      if (!Number.isFinite(seconds) || seconds <= 0) return
      const existing = entries.find((entry) => entry.date === date && entry.page === page)
      if (existing) existing.seconds += seconds
      else entries.push({ date, page, seconds })
      persist()
    },
    async flush(send) {
      if (sending || !entries.length) return
      sending = true
      const batch = entries.slice(0, 50).map((entry) => ({ ...entry, seconds: Math.min(300, entry.seconds) }))
      try {
        await send(batch)
        batch.forEach((sent) => {
          const current = entries.find((entry) => entry.date === sent.date && entry.page === sent.page)
          if (current) current.seconds -= sent.seconds
        })
        entries = entries.filter((entry) => entry.seconds > 0)
        persist()
      } finally { sending = false }
    },
  }
  screenTimeQueues.set(key, queue)
  return queue
}
