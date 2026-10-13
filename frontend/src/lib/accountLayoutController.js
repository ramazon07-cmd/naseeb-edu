import { normalizeDashboardPreferences } from '../dashboardPreferences.js';
import { hasPendingLayout, readCachedLayout, saveDashboardLayout, syncDashboardLayout } from '../dashboardLayoutSync.js';

// Serializes writes and versions local choices, including choices made while
// the first GET is waiting. Dependency injection keeps races deterministic in tests.
export function createAccountLayoutController({ storage, fetchLayout, saveLayout }) {
  const sessions = new Map();
  const get = (id) => {
    if (!sessions.has(id)) sessions.set(id, { revision: 0, load: null, latest: null, writes: Promise.resolve(), listeners: new Set(), pending: hasPendingLayout(storage, id) });
    return sessions.get(id);
  };
  const publish = (state, layout) => state.listeners.forEach((listener) => listener({ layout, pending: state.pending }));
  function send(state, layout, current) {
    const write = state.writes.then(() => current() ? saveLayout(layout) : undefined);
    state.writes = write.catch(() => {});
    return write;
  }
  function load(id) {
    const state = get(id);
    if (state.load) return state.load;
    const revision = state.revision;
    const current = () => sessions.get(id) === state && state.revision === revision;
    const pending = syncDashboardLayout({
      storage, userId: id, fetchLayout, isCurrent: current, pendingLayout: state.pending ? state.latest : null,
      saveLayout: (layout) => send(state, layout, current),
    }).then((result) => {
      if (!current()) return state.latest || normalizeDashboardPreferences(readCachedLayout(storage, id));
      state.latest = result.layout;
      state.pending = !result.synced && (state.pending || hasPendingLayout(storage, id));
      if (!result.synced && state.load === pending) state.load = null;
      publish(state, result.layout);
      return result.layout;
    });
    state.load = pending;
    return pending;
  }
  return {
    load,
    async save(id, layout) {
      const state = get(id);
      const revision = ++state.revision;
      state.latest = layout;
      state.pending = true;
      state.load = null;
      const current = () => sessions.get(id) === state && state.revision === revision;
      const result = await saveDashboardLayout({
        storage, userId: id, layout, isCurrent: current,
        saveLayout: (value) => send(state, value, current),
      });
      if (current()) {
        state.pending = !result.synced;
        state.load = result.synced ? Promise.resolve(layout) : null;
        publish(state, layout);
      }
      return result;
    },
    subscribe(id, listener) {
      const state = get(id);
      state.listeners.add(listener);
      return () => state.listeners.delete(listener);
    },
    isPending: (id) => get(id).pending,
    clear() { sessions.clear(); },
  };
}
