import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { appendRows, canLoadMore, subjectRankingsPath } from '../lib/subjectRankings';

// One page of the QS subject ranking, through the generic page request: api.js (the start-up bundle) has no
// method of its own for it.
const fetchPage = (path, signal) => api.page('subject-rankings', `?${path}`, signal);

const INITIAL = { query: null, subject: null, rows: [], count: 0, year: null, indicators: [], nextOffset: null, loading: true, loadingMore: false, error: '' };

/**
 * One subject ranking, one page at a time. `query` comes from subjectRankingsQuery() (null waits: nothing
 * is requested). The first page is fetched when the query changes; "Show more" fetches the page after the
 * rows already shown. Only the loaded pages of the current subject are kept, in memory: a new subject drops
 * them, and a request in flight is aborted the moment the subject or a filter changes.
 */
export function useSubjectRankings(query, subject) {
  const [state, setState] = useState(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const controller = useRef(null);

  useEffect(() => {
    controller.current?.abort();
    if (query == null) return undefined;
    const own = new AbortController();
    controller.current = own;
    // The rows of another subject have other columns: drop them at once. A filter change keeps the old rows (dimmed).
    setState((previous) => ({ ...(previous.subject === subject ? previous : INITIAL), loading: true, loadingMore: false, error: '' }));
    fetchPage(subjectRankingsPath(query), own.signal).then((payload) => {
      if (own.signal.aborted) return;
      setState({
        query, subject, rows: payload.results, count: payload.count, year: payload.year, indicators: payload.indicators,
        nextOffset: payload.next_offset, loading: false, loadingMore: false, error: '',
      });
    }).catch((error) => {
      if (!own.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({
        // Rows that belong to another query must not stay: "Show more" would page the new query from their offset.
        ...(previous.query === query ? previous : { ...previous, rows: [], count: 0, nextOffset: null }), loading: false, error: error.message,
      }));
    });
    return () => own.abort();
  }, [query, subject, attempt]);

  const loadMore = useCallback(() => {
    const own = controller.current;
    if (!own || !canLoadMore(state, query) || state.loading || state.loadingMore) return;
    const offset = state.nextOffset;
    setState((previous) => ({ ...previous, loadingMore: true }));
    fetchPage(subjectRankingsPath(query, offset), own.signal).then((payload) => {
      if (own.signal.aborted) return;
      setState((previous) => previous.nextOffset !== offset ? previous : {
        ...previous, rows: appendRows(previous.rows, payload.results), count: payload.count, nextOffset: payload.next_offset, loadingMore: false,
      });
    }).catch((error) => {
      if (!own.signal.aborted && error?.name !== 'AbortError') setState((previous) => ({ ...previous, loadingMore: false, error: error.message }));
    });
  }, [query, state]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { ...state, loadMore, retry };
}
