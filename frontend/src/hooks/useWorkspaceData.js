import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { t } from '../i18n';
import { busyRetryDelay } from '../lib/backoff';
import { EMPTY_DATA } from '../lib/emptyData';
import { createKeyedLatest } from '../lib/latestRequest';
import { planWorkspaceReload } from '../lib/reloadPlan';
import { PAGED_ENDPOINTS, STUDENT_SHELL_KEYS, createInFlight, failedStatsStatus, loadsDashboardStats, loadsLazily, mergeStats, missingKeys, pagedListsAfter, resourcesFor, selectWorkspaceLoad, waitsBeforeLoading } from '../lib/workspaceResources';
import { clearPagedLists, invalidatePagedLists } from './usePagedList';
import { createResourceFreshness, WORKSPACE_RESOURCES_CHANGED } from '../lib/workspaceFreshness';

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
 *
 * `statsRequest(user)`: how dashboard stats are fetched (Counselor Home asks
 * for ?include=home, so Home and the badges share one call); `statsKey(user)`
 * names that variant, so a refresh joins a load of the same stats in flight.
 *
 * `more[key]`: the next page of a first-page-only collection (null when it is
 * all here); `loadMore(key)` appends it.
 */
const defaultStatsRequest = () => api.dashboard();
const defaultStatsKey = () => 'dashboard';

export function useWorkspaceData(user, onUnauthorized, { statsRequest = defaultStatsRequest, statsKey = defaultStatsKey } = {}) {
  const statsRequestRef = useRef(statsRequest);
  statsRequestRef.current = statsRequest;
  const statsKeyRef = useRef(statsKey);
  statsKeyRef.current = statsKey;
  const statsInFlight = useRef(createInFlight());
  const [more, setMore] = useState({});
  const moreLoading = useRef(new Set());
  const [data, setData] = useState(EMPTY_DATA);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resourceStatus, setResourceStatus] = useState({});
  const latestLoads = useRef(createKeyedLatest());
  const inFlightLoads = useRef(0);
  // Keys fetched (or being fetched) at least once since sign-in.
  const requestedOnce = useRef(new Set());
  const freshness = useRef(createResourceFreshness());
  useEffect(() => {
    if (!loadsLazily(user)) return undefined;
    const invalidate = (event) => freshness.current.invalidate(event.detail || []);
    window.addEventListener(WORKSPACE_RESOURCES_CHANGED, invalidate);
    return () => window.removeEventListener(WORKSPACE_RESOURCES_CHANGED, invalidate);
  }, [user]);
  const requestedFor = useRef(null);
  // Sections refused by the rate limit (429) are retried on their own a few
  // times (status `busy`: "Busy, retrying…"); attempts per key, the keys
  // waiting, and the one timer that reloads them all.
  const busyAttempts = useRef(new Map());
  const busyPending = useRef(new Set());
  const busyTimer = useRef(null);

  // `background`: a poll. It leaves the loading flag and error banner alone, a
  // failed refresh keeps showing what was already loaded, and it leaves the
  // pending-writes log to the save that will reload with it.
  const loadData = useCallback(async (activeUser = user, requestedKeys = null, { background = false } = {}) => {
    if (waitsBeforeLoading(activeUser)) return;
    inFlightLoads.current += 1;
    if (!background) {setLoading(true);setError('');}
    try {
      const resources = resourcesFor(activeUser);
      // A save only refetches the resources it wrote (plus derived stats and
      // student progress); unknown writes still trigger a full reload.
      const written = background ? [] : api.takeMutations();
      if (written.length) invalidatePagedLists(pagedListsAfter(written));
      const changed = requestedKeys === RELOAD_CHANGED;
      const planned = changed ? planWorkspaceReload(written, resources, ['dashboard', 'students'], PAGED_ENDPOINTS) : requestedKeys;
      const selected = selectWorkspaceLoad(activeUser, planned, requestedOnce.current, { changed });
      selected.forEach(([key]) => requestedOnce.current.add(key));
      const settleFreshness = freshness.current.begin(selected.map(([key]) => key));
      // `loaded` stays true once a key has arrived, so a page can tell its
      // first load (skeleton) from a background refresh (keep showing data).
      setResourceStatus((current) => {
        const next = { ...current };
        selected.forEach(([key]) => {
          if (background && current[key]?.loaded) return;
          next[key] = { status: 'loading', error: '', loaded: Boolean(current[key]?.loaded) };
        });
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
      // A save's reload always asks afresh (and becomes the request a Home refresh joins).
      const fetchStats = () => statsInFlight.current.track(statsKeyRef.current(activeUser), statsRequestRef.current(activeUser));
      const nextPages = {};
      const firstPage = (key, endpoint, query) => api.page(endpoint, query).then((payload) => {
        if (!Array.isArray(payload?.results)) return payload ?? [];
        nextPages[key] = payload.next || null;
        return payload.results;
      });
      const requests = selected.map(([key, endpoint, query = '', options = {}]) => [
        key,
        key === 'dashboard' ? fetchStats
          : options.firstPage ? () => firstPage(key, endpoint, query)
            : () => api.list(endpoint, query, { onPage: showPartial(key) }),
      ]);
      const settled = await Promise.allSettled(requests.map(([, request]) => request()));
      const successfulResources = {};
      const nextStatuses = {};
      let dashboardStats;
      let unauthorized = false;
      const busyKeys = [];
      let busyWait = 0;
      settled.forEach((result, index) => {
        const key = requests[index][0];
        if (!isCurrent(key)) return;
        settleFreshness(key, result.status === 'fulfilled');
        if (result.status === 'fulfilled') {
          busyAttempts.current.delete(key);
          nextStatuses[key] = { status: 'success', error: '', loaded: true };
          if (key === 'dashboard') dashboardStats = result.value;else
          successfulResources[key] = result.value || [];
        } else {
          unauthorized ||= result.reason?.status === 401;
          // A poll that hits the rate limit backs off on its own poller instead.
          const attempt = busyAttempts.current.get(key) || 0;
          const wait = background ? null : busyRetryDelay(attempt, result.reason);
          if (wait != null) {
            busyAttempts.current.set(key, attempt + 1);
            busyKeys.push(key);
            busyWait = Math.max(busyWait, wait);
            nextStatuses[key] = { status: 'loading', busy: true, error: '', loaded: false };
            return;
          }
          busyAttempts.current.delete(key);
          nextStatuses[key] = { status: 'error', error: result.reason?.message || 'Unable to load this section.', loaded: false };
        }
      });
      if (unauthorized) {
        onUnauthorized();
        return;
      }
      if (dashboardStats !== undefined) setStats((current) => mergeStats(current, dashboardStats));
      if (Object.keys(successfulResources).length) {
        setData((current) => ({ ...current, ...successfulResources }));
        const paged = Object.keys(successfulResources).filter((key) => key in nextPages);
        if (paged.length) setMore((current) => ({ ...current, ...Object.fromEntries(paged.map((key) => [key, nextPages[key]])) }));
      }
      setResourceStatus((current) => {
        const next = { ...current };
        Object.entries(nextStatuses).forEach(([key, status]) => {
          if (background && status.status === 'error' && current[key]?.loaded && !loadsLazily(activeUser)) return;
          next[key] = { ...status, loaded: status.loaded || Boolean(current[key]?.loaded) };
        });
        return next;
      });
      if (busyKeys.length) {
        busyKeys.forEach((key) => busyPending.current.add(key));
        window.clearTimeout(busyTimer.current);
        busyTimer.current = window.setTimeout(() => {
          const keys = [...busyPending.current];
          busyPending.current.clear();
          busyTimer.current = null;
          loadData(activeUser, keys);
        }, busyWait);
      }
      if (!background && !busyKeys.length && settled.length > 0 && settled.every((result) => result.status === 'rejected')) {
        setError(t("No new information could be loaded. Check your connection and retry."));
      }
      // A write may have invalidated a collection while its read was waiting.
      // Follow that successful, now-stale read once; failed reads use normal backoff.
      const invalidated = loadsLazily(activeUser) ? freshness.current.due(Object.keys(successfulResources)) : [];
      if (invalidated.length) queueMicrotask(() => loadData(activeUser, invalidated, { background: true }));
      return settled.every((result) => result.status === 'fulfilled');
    } catch (err) {
      if (!background) setError(err.message);
      return false;
    } finally {
      inFlightLoads.current -= 1;
      if (inFlightLoads.current === 0) setLoading(false);
    }
  }, [user, onUnauthorized]);

  // Stats alone (the minute poll, Counselor Home): resolves to the response,
  // rejects on failure so the caller can back off or show the error.
  // While a load of the same stats is in flight it is joined, not superseded:
  // that load writes the result (or its error) and this resolves with it.
  const refreshStats = useCallback(async (activeUser = user) => {
    if (waitsBeforeLoading(activeUser) || !loadsDashboardStats(activeUser)) return null;
    const key = statsKeyRef.current(activeUser);
    const running = statsInFlight.current.join(key);
    if (running) return running;
    const isCurrent = latestLoads.current.start(['dashboard']);
    let next;
    try {
      next = await statsInFlight.current.track(key, statsRequestRef.current(activeUser));
    } catch (err) {
      // This request superseded any load of the key, so it settles the status.
      if (isCurrent('dashboard')) setResourceStatus((current) => ({ ...current, dashboard: failedStatsStatus(current.dashboard, err) }));
      throw err;
    }
    if (isCurrent('dashboard')) {
      setStats((current) => mergeStats(current, next));
      setResourceStatus((current) => ({ ...current, dashboard: { status: 'success', error: '', loaded: true } }));
    }
    return next;
  }, [user]);

  // Fetch the keys this user's workspace has not requested yet (a student
  // opening a page). Fresh keys and keys in flight are not fetched twice.
  const ensureLoaded = useCallback((activeUser, keys) => {
    if (waitsBeforeLoading(activeUser)) return Promise.resolve();
    const missing = missingKeys(activeUser, keys, requestedOnce.current);
    const stale = loadsLazily(activeUser) ? freshness.current.due(keys).filter((key) => requestedOnce.current.has(key)) : [];
    const wanted = [...new Set([...missing, ...stale])];
    return wanted.length ? loadData(activeUser, wanted) : Promise.resolve();
  }, [loadData]);

  const revalidate = useCallback(async (activeUser, keys) => {
    if (waitsBeforeLoading(activeUser) || !loadsLazily(activeUser)) return true;
    const available = new Set(resourcesFor(activeUser).map(([key]) => key));
    const due = freshness.current.due(keys.filter((key) => available.has(key)));
    if (!due.length) return true;
    return (await loadData(activeUser, due, { background: true })) ? true : null;
  }, [loadData]);

  // Sign-out: drop in-flight responses and everything loaded for the user.
  const reset = useCallback(() => {
    latestLoads.current.cancelAll();
    window.clearTimeout(busyTimer.current);
    busyTimer.current = null;
    busyPending.current.clear();
    busyAttempts.current = new Map();
    statsInFlight.current.clear();
    setMore({});
    requestedOnce.current = new Set();
    freshness.current.clear();
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

  // The next page of a first-page-only collection, appended (rows already
  // here, e.g. after a reload moved them, are not repeated).
  const loadMore = useCallback(async (key) => {
    const next = more[key];
    if (!next || moreLoading.current.has(key)) return;
    moreLoading.current.add(key);
    try {
      const isCurrent = latestLoads.current.start([`${key}:more`]);
      const payload = await api.pageAt(next);
      if (!isCurrent(`${key}:more`)) return;
      setData((current) => {
        const seen = new Set((current[key] || []).map((item) => item.id));
        return { ...current, [key]: [...(current[key] || []), ...(payload?.results || []).filter((item) => !seen.has(item.id))] };
      });
      setMore((current) => (current[key] === next ? { ...current, [key]: payload?.next || null } : current));
    } finally {
      moreLoading.current.delete(key);
    }
  }, [more]);

  return { data, stats, loading, error, resourceStatus, loadData, loadInitial, ensureLoaded, revalidate, reset, refreshStats, updateStats: setStats, more, loadMore };
}
