// The student dashboard layout belongs to the account (saved on the server) and
// is cached in this browser so the dashboard opens instantly and still works
// offline. Framework-free and storage/API-injected so it is unit tested.
import { normalizeDashboardPreferences } from './dashboardPreferences.js';
import { userStorageKey } from './userStorage.js';

// The cache key predates server sync: a layout saved there by an earlier
// version is uploaded once when the account has none yet.
export const DASHBOARD_LAYOUT_CACHE = 'naseeb-dashboard-v1';
// Set while the newest local change has not reached the server yet.
export const DASHBOARD_LAYOUT_PENDING = 'naseeb-dashboard-pending-v1';

function resolve(storage) {
  try { return typeof storage === 'function' ? storage() : storage; } catch { return null; }
}

export function readCachedLayout(storage, userId) {
  const target = resolve(storage);
  try {
    const raw = target?.getItem(userStorageKey(DASHBOARD_LAYOUT_CACHE, userId));
    const value = raw ? JSON.parse(raw) : null;
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch { return null; }
}

export function hasPendingLayout(storage, userId) {
  try { return resolve(storage)?.getItem(userStorageKey(DASHBOARD_LAYOUT_PENDING, userId)) === '1'; } catch { return false; }
}

// Returns false when this browser cannot store it (private mode, quota).
export function writeCachedLayout(storage, userId, layout, { pending = false } = {}) {
  const target = resolve(storage);
  if (!target) return false;
  try {
    target.setItem(userStorageKey(DASHBOARD_LAYOUT_CACHE, userId), JSON.stringify(layout));
    if (pending) target.setItem(userStorageKey(DASHBOARD_LAYOUT_PENDING, userId), '1');
    else target.removeItem(userStorageKey(DASHBOARD_LAYOUT_PENDING, userId));
    return true;
  } catch { return false; }
}

/**
 * Which layout wins when the dashboard opens:
 *   - a local change that never reached the server (made offline) -> upload it;
 *   - otherwise the account's layout;
 *   - no account layout but one cached here (saved before server sync) -> upload it once;
 *   - neither -> the default layout.
 */
export function planLayoutSync({ server, local, pending }) {
  if (pending && local) return { layout: local, upload: true };
  if (server) return { layout: server, upload: false };
  if (local) return { layout: local, upload: true };
  return { layout: null, upload: false };
}

// Reconciles the cache with the account. Resolves to { layout, online }: the
// normalized layout, and whether the account could be read at all.
// `fetchLayout()` resolves to { layout } and `saveLayout(layout)` stores it.
export async function syncDashboardLayout({ storage, userId, fetchLayout, saveLayout }) {
  const local = readCachedLayout(storage, userId);
  const pending = hasPendingLayout(storage, userId);
  let server;
  try {
    server = (await fetchLayout())?.layout ?? null;
  } catch {
    // Offline or server trouble: the cached layout is the best we have.
    return { layout: normalizeDashboardPreferences(local), online: false };
  }
  const plan = planLayoutSync({ server, local, pending });
  const layout = normalizeDashboardPreferences(plan.layout);
  if (plan.upload) {
    try {
      await saveLayout(layout);
      writeCachedLayout(storage, userId, layout);
    } catch {
      writeCachedLayout(storage, userId, layout, { pending: true });
    }
  } else if (plan.layout) {
    writeCachedLayout(storage, userId, layout);
  }
  return { layout, online: true };
}

// Saves a layout the user chose: cached first (so it applies even offline),
// then sent to the account. Resolves to { synced, cached }.
export async function saveDashboardLayout({ storage, userId, layout, saveLayout }) {
  const cached = writeCachedLayout(storage, userId, layout, { pending: true });
  try {
    await saveLayout(layout);
    if (cached) writeCachedLayout(storage, userId, layout);
    return { synced: true, cached };
  } catch {
    return { synced: false, cached };
  }
}
