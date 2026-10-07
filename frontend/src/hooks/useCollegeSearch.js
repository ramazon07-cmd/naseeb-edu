import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';

// After a page arrives, the next one waits this long before it is fetched, so on
// a slow connection the rows on screen always come first.
const PREFETCH_DELAY_MS = 800;
// Pages kept in memory, so going back to an earlier filter is instant.
const CACHED_PAGES = 40;

const INITIAL = { query: null, rows: [], count: 0, next: null, facets: null, loading: true, loadingMore: false, error: '' };

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
  const pages = useRef(new Map());
  const controller = useRef(null);
  const prefetchTimer = useRef(0);

  // A page in flight belongs to the search that asked for it: once that search is
  // cancelled (its signal aborted) the request is never handed out again. A page
  // that has arrived stays reusable.
  const page = useCallback((number) => {
    const key = `${version}|${query}|${number}`;
    const cached = pages.current.get(key);
    if (cached && (cached.done || !cached.signal?.aborted)) return cached.promise;
    const signal = controller.current?.signal;
    const promise = api.collegeSearch(`${query}&page=${number}${number === 1 ? '&facets=true' : ''}`, signal);
    const entry = { promise, signal };
    pages.current.set(key, entry);
    promise.then(() => {entry.done = true;}, () => {if (pages.current.get(key) === entry) pages.current.delete(key);});
    if (pages.current.size > CACHED_PAGES) pages.current.delete(pages.current.keys().next().value);
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
        query, rows: payload.results, count: payload.count, next: payload.next,
        facets: payload.facets || previous.facets, loading: false, loadingMore: false, error: '',
      }));
      prefetch(payload.next);
    }).catch((error) => {
      if (!own.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({ ...previous, loading: false, error: error.message }));
    });
    return () => {
      own.abort();
      window.clearTimeout(prefetchTimer.current);
    };
  }, [page, prefetch, query, attempt]);

  const loadMore = useCallback(() => {
    const number = state.next;
    if (!number || state.loadingMore || state.loading) return;
    const own = controller.current;
    setState((previous) => ({ ...previous, loadingMore: true }));
    page(number).then((payload) => {
      if (own?.signal.aborted) return;
      setState((previous) => {
        if (previous.next !== number) return previous;
        const seen = new Set(previous.rows.map((row) => row.id));
        return { ...previous, rows: [...previous.rows, ...payload.results.filter((row) => !seen.has(row.id))], count: payload.count, next: payload.next, loadingMore: false };
      });
      prefetch(payload.next);
    }).catch((error) => {
      if (!own?.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({ ...previous, loadingMore: false, error: error.message }));
    });
  }, [page, prefetch, state.next, state.loadingMore, state.loading]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { ...state, loadMore, retry };
}
