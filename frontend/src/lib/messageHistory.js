// A chat's loaded history, oldest first. Polls bring back the newest page;
// "load older" prepends pages fetched with ?before=<oldest id>. Framework-free
// so the merging rules are unit tested.

// The server's timeline order: created_at, then id for equal timestamps.
export function compareMessages(a, b) {
  const byTime = new Date(a.created_at) - new Date(b.created_at);
  return byTime || a.id - b.id;
}

// `page` is the newest page, oldest first. Rows older than it stay (they may
// be pages the user loaded, or rows that slid out of the window since the
// last poll); everything from the page's first row on is replaced by it.
export function mergeNewestPage(current, page) {
  if (!page.length) return current.length ? [] : current;
  const first = page[0];
  const kept = current.filter((message) => compareMessages(message, first) < 0);
  return [...kept, ...page];
}

// `older` is a page fetched before the oldest loaded message, oldest first.
export function prependOlder(current, older) {
  const loaded = new Set(current.map((message) => message.id));
  return [...older.filter((message) => !loaded.has(message.id)), ...current];
}

// Distance from the bottom, kept across a prepend so the view does not jump.
export const scrollAnchor = (list) => (list ? list.scrollHeight - list.scrollTop : null);
export const restoredScrollTop = (list, anchor) => Math.max(0, list.scrollHeight - anchor);
