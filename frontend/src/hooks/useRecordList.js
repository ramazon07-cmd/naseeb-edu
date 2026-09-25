import { useMemo } from 'react';
import { matchesQuery } from '../lib/searchIndex';
import { usesPagedLists } from '../lib/workspaceResources';
import { usePagedList } from './usePagedList';

const NOOP = () => {};

/**
 * Records for a list page. Staff get a server-paged, server-searched list
 * (their scope can hold tens of thousands of rows); students and parents
 * keep filtering their own small collection already in memory.
 *
 * endpoint:    API path ('tasks', 'roadmap-missions', …)
 * dataKey:     key in workspace data for the in-memory mode
 * filters:     server filters ({ student, status, … })
 * localFilter: the same restriction applied to in-memory rows
 */
export function useRecordList({ user, data, endpoint, dataKey = endpoint, query = '', filters = {}, localFilter = null, ordering = '', pageSize, enabled = true }) {
  const paged = enabled && usesPagedLists(user);
  const list = usePagedList(endpoint, { search: query, filters, ordering, pageSize, enabled: paged });
  const source = data?.[dataKey];
  const localItems = useMemo(() => {
    if (paged) return [];
    return (Array.isArray(source) ? source : []).filter((item) => (!localFilter || localFilter(item)) && matchesQuery(item, query));
  }, [paged, source, localFilter, query]);
  if (paged) return { ...list, paged: true };
  return { items: localItems, loaded: true, loading: false, loadingMore: false, hasMore: false, error: '', loadMore: NOOP, reload: NOOP, updateItem: NOOP, paged: false };
}
