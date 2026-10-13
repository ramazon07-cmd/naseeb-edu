export const STUDENT_REFRESH_MS = 60_000;
export const WORKSPACE_RESOURCES_CHANGED = 'naseeb:workspace-resources-changed';

// Tracks successful reads, failed attempts and writes made while a read is
// in flight. A stale response cannot clear a newer invalidation.
export function createResourceFreshness({ now = Date.now, ttl = STUDENT_REFRESH_MS } = {}) {
  const entries = new Map();
  let serial = 0;
  return {
    begin(keys) {
      const tokens = new Map();
      for (const key of keys) {
        const previous = entries.get(key) || { revision: 0, dirty: false };
        const token = ++serial;
        entries.set(key, { ...previous, token, busy: true, at: now() });
        tokens.set(key, { token, revision: previous.revision });
      }
      return (key, success) => {
        const current = entries.get(key);
        const mine = tokens.get(key);
        if (!current || current.token !== mine?.token) return;
        entries.set(key, { ...current, busy: false, at: now(), dirty: success && current.revision === mine.revision ? false : current.dirty });
      };
    },
    due(keys, { force = false } = {}) {
      return [...new Set(keys)].filter((key) => {
        const entry = entries.get(key);
        return !entry?.busy && (!entry || force || entry.dirty || now() - entry.at >= ttl);
      });
    },
    invalidate(keys) {
      for (const key of keys) {
        const previous = entries.get(key) || { revision: 0 };
        entries.set(key, { ...previous, revision: previous.revision + 1, dirty: true });
      }
    },
    clear() { entries.clear(); },
  };
}
