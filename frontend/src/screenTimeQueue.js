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
