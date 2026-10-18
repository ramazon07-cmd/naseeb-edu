// Account-scoped layout sync; writes and slow initial reads are versioned.
import { api } from './api';
import { readCachedLayout } from './dashboardLayoutSync';
import { createAccountLayoutController } from './lib/accountLayoutController';

const browserStorage = () => window.localStorage;
const controller = createAccountLayoutController({ storage: browserStorage, fetchLayout: api.dashboardLayout, saveLayout: api.saveDashboardLayout });

export const cachedDashboardLayout = (userId) => readCachedLayout(browserStorage, userId);
export const loadAccountDashboardLayout = (userId) => controller.load(userId);
export const saveAccountDashboardLayout = (userId, layout) => controller.save(userId, layout);
export const subscribeDashboardLayout = (userId, listener) => controller.subscribe(userId, listener);
export const pendingDashboardLayout = (userId) => controller.isPending(userId);
export const forgetAccountDashboardLayout = () => controller.clear();
