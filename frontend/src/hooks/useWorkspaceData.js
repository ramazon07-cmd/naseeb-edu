import { useCallback, useRef, useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { EMPTY_DATA } from '../lib/emptyData';
import { createKeyedLatest } from '../lib/latestRequest';
import { planWorkspaceReload } from '../lib/reloadPlan';
import { PAGED_ENDPOINTS, loadsDashboardStats, pagedListsAfter, resourcesFor, waitsBeforeLoading } from '../lib/workspaceResources';
import { clearPagedLists, invalidatePagedLists } from './usePagedList';

// loadData(user, RELOAD_CHANGED): refetch what the last saves touched.
export const RELOAD_CHANGED = 'changed';

/**
 * Workspace data for the signed-in user: every collection their role sees,
 * dashboard stats and per-resource loading state. `onUnauthorized` runs when
 * a load comes back 401 after the token refresh already failed.
 */
export function useWorkspaceData(user, onUnauthorized) {
  const [data, setData] = useState(EMPTY_DATA);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resourceStatus, setResourceStatus] = useState({});
  const latestLoads = useRef(createKeyedLatest());
  const inFlightLoads = useRef(0);

  const loadData = useCallback(async (activeUser = user, requestedKeys = null) => {
    if (waitsBeforeLoading(activeUser)) return;
    inFlightLoads.current += 1;
    setLoading(true);setError('');
    try {
      const resources = resourcesFor(activeUser);
      // A save only refetches the resources it wrote (plus derived stats and
      // student progress); unknown writes still trigger a full reload.
      const written = api.takeMutations();
      invalidatePagedLists(pagedListsAfter(written));
      const planned = requestedKeys === RELOAD_CHANGED ? planWorkspaceReload(written, resources, ['dashboard', 'students'], PAGED_ENDPOINTS) : requestedKeys;
      const requested = planned ? new Set(planned) : null;
      const selected = [
      ...(loadsDashboardStats(activeUser) ? [['dashboard']] : []),
      ...resources].
      filter(([key]) => !requested || requested.has(key));
      setResourceStatus((current) => {
        const next = { ...current };
        selected.forEach(([key]) => {next[key] = { status: 'loading', error: '' };});
        return next;
      });
      // Only the newest request per key may write: an older, slower reload
      // must not overwrite fresher data (or data of a user who signed out).
      const isCurrent = latestLoads.current.start(selected.map(([key]) => key));
      // The first page of a multi-page collection renders at once; later
      // pages fill in as they arrive.
      const showPartial = (key) => (items) => {
        if (isCurrent(key)) setData((current) => ({ ...current, [key]: items }));
      };
      const requests = selected.map(([key, endpoint, query = '']) => [
        key,
        key === 'dashboard' ? () => api.dashboard() : () => api.list(endpoint, query, { onPage: showPartial(key) }),
      ]);
      const settled = await Promise.allSettled(requests.map(([, request]) => request()));
      const successfulResources = {};
      const nextStatuses = {};
      let dashboardStats;
      let unauthorized = false;
      settled.forEach((result, index) => {
        const key = requests[index][0];
        if (!isCurrent(key)) return;
        if (result.status === 'fulfilled') {
          nextStatuses[key] = { status: 'success', error: '' };
          if (key === 'dashboard') dashboardStats = result.value;else
          successfulResources[key] = result.value || [];
        } else {
          unauthorized ||= result.reason?.status === 401;
          nextStatuses[key] = { status: 'error', error: result.reason?.message || 'Unable to load this section.' };
        }
      });
      if (unauthorized) {
        onUnauthorized();
        return;
      }
      if (dashboardStats !== undefined) setStats(dashboardStats);
      if (Object.keys(successfulResources).length) {
        setData((current) => ({ ...current, ...successfulResources }));
      }
      setResourceStatus((current) => ({ ...current, ...nextStatuses }));
      if (settled.length > 0 && settled.every((result) => result.status === 'rejected')) {
        setError(t("No new information could be loaded. Check your connection and retry."));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      inFlightLoads.current -= 1;
      if (inFlightLoads.current === 0) setLoading(false);
    }
  }, [user, onUnauthorized]);

  // Sign-out: drop in-flight responses and everything loaded for the user.
  const reset = useCallback(() => {
    latestLoads.current.cancelAll();
    clearPagedLists();
    setData(EMPTY_DATA);
    setStats(null);
    setResourceStatus({});
  }, []);

  return { data, stats, loading, error, resourceStatus, loadData, reset };
}
