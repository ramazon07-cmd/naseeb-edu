import { useCallback, useRef, useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { EMPTY_DATA } from '../lib/emptyData';
import { createKeyedLatest } from '../lib/latestRequest';
import { planWorkspaceReload } from '../lib/reloadPlan';
import { PAGED_ENDPOINTS, STUDENT_SHELL_KEYS, loadsLazily, missingKeys, pagedListsAfter, resourcesFor, selectWorkspaceLoad, waitsBeforeLoading } from '../lib/workspaceResources';
import { clearPagedLists, invalidatePagedLists } from './usePagedList';

// loadData(user, RELOAD_CHANGED): refetch what the last saves touched.
export const RELOAD_CHANGED = 'changed';

/**
 * Workspace data for the signed-in user: every collection their role sees,
 * dashboard stats and per-resource loading state. `onUnauthorized` runs when
 * a load comes back 401 after the token refresh already failed.
 *
 * Students load lazily (lib/workspaceResources loadsLazily): `loadInitial`
 * fetches only the shell's collections and `ensureLoaded` fetches a page's
 * collections the first time it opens; reloads refetch only what was loaded.
 * Every other role loads everything in `loadInitial`, exactly as `loadData`.
 */
export function useWorkspaceData(user, onUnauthorized) {
  const [data, setData] = useState(EMPTY_DATA);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resourceStatus, setResourceStatus] = useState({});
  const latestLoads = useRef(createKeyedLatest());
  const inFlightLoads = useRef(0);
  // Keys fetched (or being fetched) at least once since sign-in.
  const requestedOnce = useRef(new Set());
  const requestedFor = useRef(null);

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
      const changed = requestedKeys === RELOAD_CHANGED;
      const planned = changed ? planWorkspaceReload(written, resources, ['dashboard', 'students'], PAGED_ENDPOINTS) : requestedKeys;
      const selected = selectWorkspaceLoad(activeUser, planned, requestedOnce.current, { changed });
      selected.forEach(([key]) => requestedOnce.current.add(key));
      // `loaded` stays true once a key has arrived, so a page can tell its
      // first load (skeleton) from a background refresh (keep showing data).
      setResourceStatus((current) => {
        const next = { ...current };
        selected.forEach(([key]) => {next[key] = { status: 'loading', error: '', loaded: Boolean(current[key]?.loaded) };});
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
          nextStatuses[key] = { status: 'success', error: '', loaded: true };
          if (key === 'dashboard') dashboardStats = result.value;else
          successfulResources[key] = result.value || [];
        } else {
          unauthorized ||= result.reason?.status === 401;
          nextStatuses[key] = { status: 'error', error: result.reason?.message || 'Unable to load this section.', loaded: false };
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
      setResourceStatus((current) => {
        const next = { ...current };
        Object.entries(nextStatuses).forEach(([key, status]) => {next[key] = { ...status, loaded: status.loaded || Boolean(current[key]?.loaded) };});
        return next;
      });
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

  // Fetch the keys this user's workspace has not requested yet (a student
  // opening a page for the first time). Keys already loaded or in flight are
  // never fetched twice.
  const ensureLoaded = useCallback((activeUser, keys) => {
    if (waitsBeforeLoading(activeUser)) return Promise.resolve();
    const missing = missingKeys(activeUser, keys, requestedOnce.current);
    return missing.length ? loadData(activeUser, missing) : Promise.resolve();
  }, [loadData]);

  // Sign-out: drop in-flight responses and everything loaded for the user.
  const reset = useCallback(() => {
    latestLoads.current.cancelAll();
    requestedOnce.current = new Set();
    requestedFor.current = null;
    clearPagedLists();
    setData(EMPTY_DATA);
    setStats(null);
    setResourceStatus({});
  }, []);

  // Sign-in: students get the shell's collections (their current page asks
  // for its own through ensureLoaded); other roles load everything. Signing
  // in again after an expired session refetches what was already loaded.
  const loadInitial = useCallback((activeUser) => {
    if (!loadsLazily(activeUser)) return loadData(activeUser);
    // Another account in this tab: nothing loaded for the last one may show.
    if (requestedFor.current !== activeUser?.id) {
      if (requestedFor.current !== null) reset();
      requestedFor.current = activeUser?.id;
    }
    return requestedOnce.current.size ? loadData(activeUser) : ensureLoaded(activeUser, STUDENT_SHELL_KEYS);
  }, [ensureLoaded, loadData, reset]);

  return { data, stats, loading, error, resourceStatus, loadData, loadInitial, ensureLoaded, reset };
}
