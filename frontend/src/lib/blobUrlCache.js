// A small LRU of object URLs keyed by (id, version). Many components show the
// same photo, and remounts are frequent, so each version is fetched once and
// its blob: URL is shared. Evicted URLs are revoked to release the blob.
export function createBlobUrlCache({
  max = 64,
  createUrl = (blob) => URL.createObjectURL(blob),
  revokeUrl = (url) => URL.revokeObjectURL(url),
} = {}) {
  // key -> { url, promise }; Map order is recency order (oldest first).
  const entries = new Map()

  function touch(key, entry) {
    entries.delete(key)
    entries.set(key, entry)
  }

  function evict() {
    while (entries.size > max) {
      const [oldestKey, oldest] = entries.entries().next().value
      entries.delete(oldestKey)
      if (oldest.url) revokeUrl(oldest.url)
    }
  }

  return {
    // The ready URL for key, or '' (for a synchronous first render).
    peek(key) {
      const entry = entries.get(key)
      if (!entry?.url) return ''
      touch(key, entry)
      return entry.url
    },
    // Resolve key to an object URL, calling loadBlob() at most once per key
    // while it stays cached; concurrent callers share the same request.
    load(key, loadBlob) {
      const existing = entries.get(key)
      if (existing) {
        touch(key, existing)
        return existing.url ? Promise.resolve(existing.url) : existing.promise
      }
      const entry = { url: '', promise: null, cleared: false }
      entry.promise = Promise.resolve().then(loadBlob).then((blob) => {
        if (entry.cleared) throw new Error('Blob cache was cleared')
        entry.url = createUrl(blob)
        // Evicted while loading: a caller still wants it, so it becomes the
        // most recent entry again.
        if (entries.get(key) !== entry) {
          touch(key, entry)
          evict()
        }
        return entry.url
      }, (error) => {
        if (entries.get(key) === entry) entries.delete(key)
        throw error
      })
      entries.set(key, entry)
      evict()
      return entry.promise
    },
    clear() {
      for (const entry of entries.values()) {
        entry.cleared = true
        if (entry.url) revokeUrl(entry.url)
      }
      entries.clear()
    },
    get size() { return entries.size },
  }
}
