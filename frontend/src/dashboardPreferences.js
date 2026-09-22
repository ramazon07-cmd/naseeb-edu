export const DASHBOARD_WIDGETS = ['journey', 'meetings', 'applications', 'tasks', 'team', 'roadmap', 'discovery'];
export function normalizeDashboardPreferences(value) {
  const clean = (items) => Array.isArray(items) ? [...new Set(items.filter((id) => DASHBOARD_WIDGETS.includes(id)))] : [];
  // Upgrade the previous default arrangement, while retaining user-customized layouts.
  const oldDefault = JSON.stringify(value?.order) === JSON.stringify(['journey', 'tasks', 'meetings', 'applications', 'discovery', 'team']) && !value?.hidden?.length && JSON.stringify(value?.rail) === JSON.stringify(['discovery', 'team']);
  if (oldDefault) value = null;
  const order = clean(value?.order);
  const hidden = clean(value?.hidden);
  return {
    order: [...order, ...DASHBOARD_WIDGETS.filter((id) => !order.includes(id))],
    hidden: hidden.length === DASHBOARD_WIDGETS.length ? hidden.slice(1) : hidden,
    rail: Array.isArray(value?.rail) ? clean(value.rail) : ['roadmap', 'discovery'],
  };
}
export function moveDashboardWidget(preferences, id, column, beforeId = null) {
  if (!DASHBOARD_WIDGETS.includes(id)) return preferences;
  const next = normalizeDashboardPreferences(preferences);
  next.rail = next.rail.filter((key) => key !== id);
  if (column === 'rail') next.rail.push(id);
  next.hidden = next.hidden.filter((key) => key !== id);
  next.order = next.order.filter((key) => key !== id);
  const index = next.order.indexOf(beforeId);
  next.order.splice(index < 0 ? next.order.length : index, 0, id);
  return next;
}
