// Record filtering without JSON.stringify on every keystroke: the lowercased
// text of a record is computed once per record object (records are replaced,
// not mutated, when data reloads) and reused.
const cache = new WeakMap();

export function searchText(item, localeTag = '') {
  if (item === null || typeof item !== 'object') return String(JSON.stringify(item) ?? '').toLocaleLowerCase(localeTag || undefined);
  let perLocale = cache.get(item);
  if (!perLocale) {
    perLocale = new Map();
    cache.set(item, perLocale);
  }
  if (!perLocale.has(localeTag)) perLocale.set(localeTag, JSON.stringify(item).toLocaleLowerCase(localeTag || undefined));
  return perLocale.get(localeTag);
}

// Same semantics as JSON.stringify(item).toLowerCase().includes(query.toLowerCase()).
export function matchesQuery(item, query, localeTag = '') {
  const term = String(query ?? '').toLocaleLowerCase(localeTag || undefined);
  return !term || searchText(item, localeTag).includes(term);
}

// Builds a reusable index: [{ ...meta, haystack }] once, then filters it.
export function buildIndex(entries, toText, localeTag = '') {
  return entries.map((entry) => ({ entry, haystack: String(toText(entry)).toLocaleLowerCase(localeTag || undefined) }));
}

export function searchIndex(index, query, localeTag = '', limit = Infinity) {
  const term = String(query ?? '').trim().toLocaleLowerCase(localeTag || undefined);
  if (!term) return [];
  const out = [];
  for (const { entry, haystack } of index) {
    if (haystack.includes(term)) {
      out.push(entry);
      if (out.length >= limit) break;
    }
  }
  return out;
}

// Header search = what is already in memory (pages, a student's own records)
// plus the server's top matches for records that are not (/api/search/).
// remote: { type: [{ id, title, subtitle }] }; destinations: type -> page or
// null when this user has no page for that type.
export function remoteSearchEntries(remote, destinations) {
  return Object.entries(remote || {}).flatMap(([type, items]) => {
    const destination = destinations[type];
    if (!destination || !Array.isArray(items)) return [];
    return items.filter((item) => item?.title).map((item) => ({
      id: `${type}-${item.id}`, kind: 'record', destination, title: String(item.title), subtitle: item.subtitle || '', filterQuery: String(item.title),
    }));
  });
}

// Pages first, then records; a record found both locally and on the server
// is listed once.
export function mergeSearchResults(local, remote, limit = 12) {
  const seen = new Set();
  const out = [];
  const pages = local.filter((entry) => entry.kind === 'page');
  const records = [...remote, ...local.filter((entry) => entry.kind !== 'page')];
  for (const entry of [...pages, ...records]) {
    if (seen.has(entry.id)) continue;
    seen.add(entry.id);
    out.push(entry);
    if (out.length >= limit) break;
  }
  return out;
}
