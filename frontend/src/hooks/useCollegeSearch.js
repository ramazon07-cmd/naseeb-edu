import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { createPageCache, mergePage } from '../lib/pagedList';

// After a page arrives, the next one waits this long before it is fetched, so on
// a slow connection the rows on screen always come first.
const PREFETCH_DELAY_MS = 800;

const INITIAL = { query: null, version: null, rows: [], count: 0, unpricedCount: 0, next: null, facets: null, loading: true, loadingMore: false, error: '' };

/**
 * College Search, one page at a time. `query` comes from collegeSearchQuery();
 * `version` changes when the student's profile changes, because fit scores move.
 * The first page shows as soon as it arrives. Only the page after the last one
 * shown is fetched in the background, so "Show more" is usually instant without
 * ever downloading the rest of the catalogue.
 */
export function useCollegeSearch(query, version = 0) {
  const [state, setState] = useState(INITIAL);
  const [attempt, setAttempt] = useState(0);
  // Pages kept in memory (lib/pagedList), so going back to an earlier filter is instant.
  const pages = useRef(null);
  pages.current ??= createPageCache();
  // Facets count the whole catalogue, so filters and sorting do not change them:
  // they are asked for once per profile version, not with every first page.
  const facets = useRef(new Map());
  const controller = useRef(null);
  const prefetchTimer = useRef(0);

  // A page in flight belongs to the search that asked for it: once that search is
  // cancelled (its signal aborted) the request is never handed out again. A page
  // that has arrived stays reusable.
  const page = useCallback((number) => {
    const key = `${version}|${query}|${number}`;
    const cached = pages.current.get(key);
    if (cached && !cached.failed && (cached.done || !cached.signal?.aborted)) return cached.promise;
    const signal = controller.current?.signal;
    const withFacets = number === 1 && !facets.current.has(version);
    const promise = api.collegeSearch(`${query}&page=${number}${withFacets ? '&facets=true' : ''}`, signal);
    pages.current.set(key, { promise, signal });
    const entry = pages.current.get(key);
    promise.then((payload) => {
      entry.done = true;
      if (payload.facets) facets.current.set(version, payload.facets);
    }, () => {entry.failed = true;});
    return promise;
  }, [query, version]);

  const prefetch = useCallback((number) => {
    window.clearTimeout(prefetchTimer.current);
    if (number) prefetchTimer.current = window.setTimeout(() => {page(number).catch(() => {});}, PREFETCH_DELAY_MS);
  }, [page]);

  useEffect(() => {
    controller.current?.abort();
    const own = new AbortController();
    controller.current = own;
    // The rows of the previous search stay on screen (dimmed) until these arrive.
    setState((previous) => ({ ...previous, loading: true, loadingMore: false, error: '' }));
    page(1).then((payload) => {
      if (own.signal.aborted) return;
      setState((previous) => ({
        query, version, rows: payload.results, count: payload.count, unpricedCount: payload.unpriced_count ?? 0, next: payload.next,
        facets: facets.current.get(version) || payload.facets || previous.facets, loading: false, loadingMore: false, error: '',
      }));
      prefetch(payload.next);
    }).catch((error) => {
      if (!own.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({ ...previous, loading: false, error: error.message }));
    });
    return () => {
      own.abort();
      window.clearTimeout(prefetchTimer.current);
    };
  }, [page, prefetch, query, version, attempt]);

  const loadMore = useCallback(() => {
    const number = state.next;
    if (!number || state.loadingMore || state.loading) return;
    const own = controller.current;
    setState((previous) => ({ ...previous, loadingMore: true }));
    page(number).then((payload) => {
      if (own?.signal.aborted) return;
      setState((previous) => {
        if (previous.next !== number) return previous;
        return { ...previous, rows: mergePage(previous.rows, payload.results), count: payload.count, next: payload.next, loadingMore: false };
      });
      prefetch(payload.next);
    }).catch((error) => {
      if (!own?.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({ ...previous, loadingMore: false, error: error.message }));
    });
  }, [page, prefetch, state.next, state.loadingMore, state.loading]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { ...state, loadMore, retry };
}
