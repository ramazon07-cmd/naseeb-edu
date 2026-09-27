import { useEffect, useState } from 'react';
import { api } from '../api';
import { SEARCH_DEBOUNCE_MS } from '../lib/pagedList';

const EMPTY = Object.freeze({});
export const REMOTE_SEARCH_MIN_LENGTH = 2;

// Server-side matches for the header search, for records a staff member does
// not hold in memory. Debounced; a newer query aborts the older request and a
// late response for an old query is ignored.
export function useRemoteSearch(query, enabled) {
  const [state, setState] = useState({ query: '', results: EMPTY, loading: false });
  const term = String(query || '').trim();
  const active = enabled && term.length >= REMOTE_SEARCH_MIN_LENGTH;
  useEffect(() => {
    if (!active) return undefined;
    const controller = new AbortController();
    setState((current) => ({ ...current, loading: true }));
    const timer = window.setTimeout(() => {
      api.search(term, controller.signal).then((payload) => {
        if (!controller.signal.aborted) setState({ query: term, results: payload?.results || EMPTY, loading: false });
      }).catch((error) => {
        if (!controller.signal.aborted && error?.name !== 'AbortError') setState({ query: term, results: EMPTY, loading: false });
      });
    }, SEARCH_DEBOUNCE_MS);
    return () => {window.clearTimeout(timer);controller.abort();};
  }, [active, term]);
  if (!active) return { results: EMPTY, loading: false };
  return { results: state.query === term ? state.results : EMPTY, loading: state.loading || state.query !== term };
}
