import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { INITIAL_STATE, createPageCache, createPagedController } from '../lib/pagedList';

// One cache for the whole workspace: a list reopened within a minute renders
// from memory. Cleared on sign-out and after saves to that resource.
const sharedCache = createPageCache();
const liveControllers = new Set();

export function clearPagedLists() {
  sharedCache.invalidate();
}

// After a save: drop cached pages of these endpoints and refetch every list
// on screen that shows them.
export function invalidatePagedLists(resources) {
  if (!resources?.length) return;
  sharedCache.invalidate(resources);
  for (const entry of liveControllers) {
    if (resources.includes(entry.resource)) entry.controller.reload();
  }
}

const fetchPage = (resource, query, signal) => api.page(resource, query, signal);

/**
 * A server-paged, server-searched list for `resource` (an API path such as
 * 'tasks' or 'users/accounts'). `enabled: false` loads nothing (e.g. the
 * student portal, which keeps its own small collections in memory).
 */
export function usePagedList(resource, { search = '', filters = {}, ordering = '', pageSize, enabled = true } = {}) {
  const [state, setState] = useState(INITIAL_STATE);
  const controllerRef = useRef(null);
  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    if (!enabled) return undefined;
    const controller = createPagedController({ resource, fetchPage, cache: sharedCache, onChange: setState });
    const entry = { resource, controller };
    controllerRef.current = controller;
    liveControllers.add(entry);
    return () => {
      liveControllers.delete(entry);
      controller.dispose();
      if (controllerRef.current === controller) controllerRef.current = null;
      setState(INITIAL_STATE);
    };
  }, [resource, enabled]);

  useEffect(() => {
    if (!enabled) return;
    controllerRef.current?.setParams({ search, filters: JSON.parse(filterKey), ordering, pageSize });
  }, [enabled, resource, search, filterKey, ordering, pageSize]);

  const loadMore = useCallback(() => controllerRef.current?.loadMore(), []);
  const reload = useCallback(() => controllerRef.current?.reload(), []);
  const updateItem = useCallback((id, updater) => controllerRef.current?.updateItem(id, updater), []);
  return { ...state, loadMore, reload, updateItem };
}
