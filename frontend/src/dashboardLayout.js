// The signed-in student's dashboard layout, fetched once per session (started
// at sign-in) and shared by every dashboard mount.
import { api } from './api';
import { readCachedLayout, saveDashboardLayout, syncDashboardLayout } from './dashboardLayoutSync';

const browserStorage = () => window.localStorage;
const loads = new Map();

export function cachedDashboardLayout(userId) {
  return readCachedLayout(browserStorage, userId);
}

export function loadAccountDashboardLayout(userId) {
  if (!loads.has(userId)) {
    const load = syncDashboardLayout({
      storage: browserStorage, userId, fetchLayout: api.dashboardLayout, saveLayout: api.saveDashboardLayout,
    }).then(({ layout, online }) => {
      // Not reached (offline): the next dashboard visit asks again.
      if (!online) loads.delete(userId);
      return layout;
    });
    loads.set(userId, load);
  }
  return loads.get(userId);
}

export async function saveAccountDashboardLayout(userId, layout) {
  const result = await saveDashboardLayout({ storage: browserStorage, userId, layout, saveLayout: api.saveDashboardLayout });
  // Not sent: the next dashboard visit retries the upload.
  if (result.synced) loads.set(userId, Promise.resolve(layout));
  else loads.delete(userId);
  return result;
}

export function forgetAccountDashboardLayout() {
  loads.clear();
}
