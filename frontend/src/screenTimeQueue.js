export function cleanScreenTimeQueue(entries, today) {
  const end = Date.parse(`${today}T00:00:00Z`);
  const start = end - 7 * 86400000;
  const grouped = new Map();
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (!entry || !/^\d{4}-\d{2}-\d{2}$/.test(entry.date)) continue;
    const date = Date.parse(`${entry.date}T00:00:00Z`);
    if (!Number.isFinite(date) || date < start || date > end || new Date(date).toISOString().slice(0, 10) !== entry.date) continue;
    if (typeof entry.page !== 'string' || !/^[a-z0-9_-]{1,80}$/.test(entry.page)) continue;
    if (!Number.isSafeInteger(entry.seconds) || entry.seconds < 1) continue;
    const key = `${entry.date}:${entry.page}`;
    const existing = grouped.get(key);
    if (existing) existing.seconds = Math.min(600, existing.seconds + entry.seconds);
    else grouped.set(key, { date: entry.date, page: entry.page, seconds: Math.min(600, entry.seconds) });
  }
  return [...grouped.values()];
}

const sameSlot = (a, b) => a.date === b.date && a.page === b.page;

export function addScreenTime(entries, date, page, seconds) {
  if (!(seconds > 0)) return entries;
  const existing = entries.find((entry) => sameSlot(entry, { date, page }));
  if (!existing) return [...entries, { date, page, seconds }];
  return entries.map((entry) => (entry === existing ? { ...entry, seconds: entry.seconds + seconds } : entry));
}

// Subtracts what the server accepted from the *latest* queue, so seconds that
// were added while the request was in flight are kept.
export function subtractSent(entries, sent) {
  return entries
    .map((entry) => {
      const done = sent.find((item) => sameSlot(item, entry));
      return done ? { ...entry, seconds: entry.seconds - done.seconds } : entry;
    })
    .filter((entry) => entry.seconds > 0);
}

import { backoffDelay } from './lib/backoff.js';

export const SCREEN_TIME_BATCH = { entries: 50, seconds: 300 };
export const SCREEN_TIME_REFRESH_MS = 60000;
// After a failed upload the next one waits a random time up to 30 s, 1, 2, 4… up to 15 min.
export const SCREEN_TIME_RETRY = { base: 30000, cap: 15 * 60000 };

/**
 * Queue of active seconds per (date, page) that survives reloads and offline
 * periods. `load()` / `save(entries)` persist it, `send(batch)` uploads a batch.
 * Only one upload runs at a time; overlapping flushes just persist. After a
 * failure, uploads pause for a jittered, growing wait; `flush({ force: true })`
 * (back online, signing out) skips the wait.
 */
export function createScreenTimeSync({ load, save, send, today, isOnline = () => true, now = () => Date.now(), random = Math.random }) {
  let entries = null;
  let sending = false;
  let failures = 0;
  let retryAt = 0;
  const current = () => {
    if (!entries) entries = load();
    entries = cleanScreenTimeQueue(entries, today());
    return entries;
  };
  const persist = () => { try { save(entries); } catch { /* the in-memory queue remains */ } };

  return {
    record(page, seconds) {
      entries = addScreenTime(current(), today(), page, seconds);
      persist();
    },
    pending: () => current().map((entry) => ({ ...entry })),
    async flush({ force = false } = {}) {
      current();
      persist();
      if (sending || !entries.length || !isOnline() || (!force && now() < retryAt)) return;
      sending = true;
      const batch = entries.slice(0, SCREEN_TIME_BATCH.entries)
        .map((entry) => ({ ...entry, seconds: Math.min(SCREEN_TIME_BATCH.seconds, entry.seconds) }));
      try {
        await send(batch);
        entries = subtractSent(current(), batch);
        persist();
        failures = 0;
        retryAt = 0;
      } catch {
        // Seconds stay queued; the next attempt waits so failing clients spread out.
        retryAt = now() + backoffDelay(failures, SCREEN_TIME_RETRY, random);
        failures += 1;
      } finally {
        sending = false;
      }
    },
  };
}
