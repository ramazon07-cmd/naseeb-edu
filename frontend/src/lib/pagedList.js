// Server-paged lists (the backend's keyset cursor contract: ?cursor= returns
// { results, next, has_more }). Framework-free so it is unit tested; the
// usePagedList hook is a thin React wrapper around createPagedController.
//
// - search is debounced (SEARCH_DEBOUNCE_MS); filter/ordering changes are not;
// - every request gets an id and an AbortController: a newer request aborts
//   the older one and a stale response can never overwrite newer state;
// - the pages loaded for each (resource, params) key are cached for
//   CACHE_TTL_MS, so going back to a list is instant and does not refetch.

export const DEFAULT_PAGE_SIZE = 25;
export const MAX_PAGE_SIZE = 100;
export const SEARCH_DEBOUNCE_MS = 300;
export const CACHE_TTL_MS = 60_000;
export const CACHE_LIMIT = 40;

function cleanFilters(filters = {}) {
  return Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== '' && value !== 'all')
    .sort(([a], [b]) => a.localeCompare(b));
}

// -> '?cursor=&page_size=25&search=...&status=...' (stable parameter order).
export function listQuery({ search = '', filters = {}, ordering = '', pageSize = DEFAULT_PAGE_SIZE, cursor = '' } = {}) {
  const params = new URLSearchParams();
  params.set('cursor', cursor || '');
  params.set('page_size', String(Math.min(Math.max(1, Number(pageSize) || DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)));
  const term = String(search || '').trim();
  if (term) params.set('search', term);
  if (ordering) params.set('ordering', ordering);
  for (const [key, value] of cleanFilters(filters)) params.set(key, String(value));
  return `?${params}`;
}

export function listKey(resource, { search = '', filters = {}, ordering = '', pageSize = DEFAULT_PAGE_SIZE } = {}) {
  return `${resource}${listQuery({ search, filters, ordering, pageSize })}`;
}

// The cursor of a `next` link, so the next request is built from our own
// parameters rather than trusting the absolute URL the server echoed.
export function cursorFromNext(next) {
  if (!next) return null;
  try {
    return new URL(next, 'http://local').searchParams.get('cursor');
  } catch {
    return null;
  }
}

// Appending must not duplicate a row (defensive: a row can move between pages
// if it is edited while the user scrolls).
export function mergePage(items, page) {
  const seen = new Set(items.map((item) => item.id));
  return [...items, ...page.filter((item) => !seen.has(item.id))];
}

export function createPageCache({ limit = CACHE_LIMIT, ttlMs = CACHE_TTL_MS, now = () => Date.now() } = {}) {
  const entries = new Map();
  return {
    get(key) {
      const entry = entries.get(key);
      if (!entry) return null;
      if (now() - entry.at > ttlMs) {
        entries.delete(key);
        return null;
      }
      // Map order doubles as recency for the LRU eviction below.
      entries.delete(key);
      entries.set(key, entry);
      return entry;
    },
    set(key, value) {
      entries.delete(key);
      entries.set(key, { ...value, at: now() });
      while (entries.size > limit) entries.delete(entries.keys().next().value);
    },
    // Drops every entry of these resources (after a save) or everything.
    invalidate(resources = null) {
      if (!resources) {
        entries.clear();
        return;
      }
      for (const key of [...entries.keys()]) {
        if (resources.some((resource) => key.startsWith(`${resource}?`))) entries.delete(key);
      }
    },
    size: () => entries.size,
  };
}

export const INITIAL_STATE = Object.freeze({ items: [], cursor: null, hasMore: false, loading: false, loadingMore: false, error: '', loaded: false });

/**
 * fetchPage(resource, query, signal) -> Promise<{ results, next, has_more }>
 * onChange(state) runs after every state change.
 */
export function createPagedController({
  resource,
  fetchPage,
  cache = null,
  onChange = () => {},
  debounceMs = SEARCH_DEBOUNCE_MS,
  schedule = (callback, ms) => setTimeout(callback, ms),
  cancelSchedule = (id) => clearTimeout(id),
}) {
  let params = null;
  let state = INITIAL_STATE;
  let requestId = 0;
  let inFlight = null;
  let timer = null;
  let disposed = false;

  const key = () => listKey(resource, params);
  const set = (patch) => {
    state = { ...state, ...patch };
    if (!disposed) onChange(state);
  };
  const abortInFlight = () => {
    inFlight?.abort();
    inFlight = null;
  };

  async function load({ append }) {
    const id = ++requestId;
    abortInFlight();
    const controller = new AbortController();
    inFlight = controller;
    const requestKey = key();
    set(append ? { loadingMore: true, error: '' } : { loading: true, error: '' });
    try {
      const page = await fetchPage(resource, listQuery({ ...params, cursor: append ? state.cursor : '' }), controller.signal);
      if (id !== requestId || disposed) return;
      const results = Array.isArray(page?.results) ? page.results : [];
      const items = append ? mergePage(state.items, results) : results;
      const cursor = cursorFromNext(page?.next);
      const hasMore = Boolean(page?.has_more ?? page?.next) && Boolean(cursor);
      cache?.set(requestKey, { items, cursor, hasMore });
      inFlight = null;
      set({ items, cursor, hasMore, loading: false, loadingMore: false, loaded: true });
    } catch (error) {
      if (id !== requestId || disposed || error?.name === 'AbortError') return;
      inFlight = null;
      set({ loading: false, loadingMore: false, error: error?.message || 'Unable to load this list.' });
    }
  }

  function showFromCacheOrLoad() {
    const cached = cache?.get(key());
    if (cached) {
      // A request for the previous parameters must not land on this list.
      requestId += 1;
      abortInFlight();
      set({ items: cached.items, cursor: cached.cursor, hasMore: cached.hasMore, loading: false, loadingMore: false, error: '', loaded: true });
      return;
    }
    load({ append: false });
  }

  return {
    getState: () => state,
    // Search changes wait for typing to pause; anything else applies at once.
    setParams(next) {
      const normalized = {
        search: String(next.search || '').trim(),
        filters: next.filters || {},
        ordering: next.ordering || '',
        pageSize: next.pageSize || DEFAULT_PAGE_SIZE,
      };
      const previous = params;
      params = normalized;
      if (previous && listKey(resource, previous) === key()) return;
      if (timer !== null) cancelSchedule(timer);
      timer = null;
      const onlySearchChanged = previous && listKey(resource, { ...previous, search: normalized.search }) === key();
      if (onlySearchChanged && debounceMs > 0) {
        // Keep showing the current rows while the user types.
        set({ loading: true, error: '' });
        timer = schedule(() => {
          timer = null;
          showFromCacheOrLoad();
        }, debounceMs);
        return;
      }
      showFromCacheOrLoad();
    },
    loadMore() {
      // While a new search is pending the cursor belongs to the old results.
      if (!params || timer !== null || !state.hasMore || state.loading || state.loadingMore) return;
      load({ append: true });
    },
    reload() {
      if (!params) return;
      cache?.invalidate([resource]);
      load({ append: false });
    },
    // Replace or drop one row locally (after an edit) without refetching.
    updateItem(id, updater) {
      const items = state.items.flatMap((item) => {
        if (item.id !== id) return [item];
        const next = updater(item);
        return next ? [next] : [];
      });
      set({ items });
    },
    dispose() {
      disposed = true;
      if (timer !== null) cancelSchedule(timer);
      abortInFlight();
    },
  };
}
