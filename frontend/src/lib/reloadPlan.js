// Decides what to refetch after a save instead of reloading every resource.
// api.js reports the path of each successful write; the first path segment
// (e.g. /tasks/12/approve/ -> "tasks") is mapped to the data keys it feeds.

export function endpointOf(path) {
  const clean = String(path || '').split('?')[0].replace(/^\/+/, '');
  const [first, second] = clean.split('/');
  if (!first) return '';
  return first === 'users' && second ? `${first}/${second}` : first;
}

// Writes that never change the workspace data useWorkspaceData loads:
// telemetry, AI, auth, and Essay Lab (it loads and updates its own essays and
// folders; its autosaves must not make the next save reload everything).
// 'notifications' and 'student-messages': read marks only change the bell and
// the counselor inbox, which keep their own state.
export const UNTRACKED_ENDPOINTS = ['screen-time', 'assistant', 'education-matches', 'auth', 'essay-lab', 'notifications', 'student-messages'];

// `ignore`: endpoints whose writes never change loaded data (telemetry, AI).
export function createMutationTracker(ignore = []) {
  const dirty = new Set();
  const skip = new Set(ignore);
  return {
    note(path) {
      const endpoint = endpointOf(path);
      if (endpoint && !skip.has(endpoint)) dirty.add(endpoint);
    },
    take() {
      const endpoints = [...dirty];
      dirty.clear();
      return endpoints;
    },
  };
}

/**
 * @param endpoints     endpoints written since the last reload
 * @param resources     [dataKey, endpoint] pairs the current role loads
 * @param alwaysKeys    keys whose values are derived from other records
 *                      (dashboard stats, student progress/XP)
 * @returns the keys to reload, or null for a full reload (unknown write, or
 *          nothing recorded, e.g. a caller that reloads after a custom action)
 */
export function planReload(endpoints, resources, alwaysKeys = []) {
  if (!endpoints.length) return null;
  const byEndpoint = new Map();
  for (const [key, endpoint] of resources) {
    byEndpoint.set(endpoint, [...(byEndpoint.get(endpoint) || []), key]);
  }
  const keys = new Set();
  for (const endpoint of endpoints) {
    const mapped = byEndpoint.get(endpoint);
    if (!mapped) return null;
    mapped.forEach((key) => keys.add(key));
  }
  const available = new Set(resources.map(([key]) => key));
  alwaysKeys.forEach((key) => { if (key === 'dashboard' || available.has(key)) keys.add(key); });
  return [...keys];
}

// Saves to endpoints that only server-paged lists show (hooks/usePagedList
// refreshes those) refetch just the derived keys (stats); they must not turn
// into a reload of the whole workspace.
export function planWorkspaceReload(endpoints, resources, alwaysKeys = [], pagedEndpoints = []) {
  const loaded = new Set(resources.map(([, endpoint]) => endpoint));
  const paged = new Set(pagedEndpoints);
  const workspaceEndpoints = endpoints.filter((endpoint) => loaded.has(endpoint) || !paged.has(endpoint));
  if (endpoints.length && !workspaceEndpoints.length) {
    const available = new Set(resources.map(([key]) => key));
    return alwaysKeys.filter((key) => key === 'dashboard' || available.has(key));
  }
  return planReload(workspaceEndpoints, resources, alwaysKeys);
}
