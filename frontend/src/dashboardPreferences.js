export const DASHBOARD_WIDGETS = ['journey', 'meetings', 'applications', 'tasks', 'team', 'screen_time', 'roadmap', 'discovery', 'programs'];
// What a student cannot hide: the goal, what to do next, progress and applications.
export const LOCKED_WIDGETS = ['journey', 'tasks', 'applications', 'roadmap'];
export const isLockedWidget = (id) => LOCKED_WIDGETS.includes(id);
const DEFAULT_RAIL = ['roadmap', 'discovery', 'programs'];
// Rail widgets added after layouts were already being saved.
const NEW_RAIL_WIDGETS = ['programs'];
export function normalizeDashboardPreferences(value) {
  const clean = (items) => Array.isArray(items) ? [...new Set(items.filter((id) => DASHBOARD_WIDGETS.includes(id)))] : [];
  // Upgrade the previous default arrangement, while retaining user-customized layouts.
  const oldDefault = JSON.stringify(value?.order) === JSON.stringify(['journey', 'tasks', 'meetings', 'applications', 'discovery', 'team']) && !value?.hidden?.length && JSON.stringify(value?.rail) === JSON.stringify(['discovery', 'team']);
  if (oldDefault) value = null;
  const order = clean(value?.order);
  // A layout saved before a widget was locked cannot keep it hidden.
  const hidden = clean(value?.hidden).filter((id) => !isLockedWidget(id));
  // A widget added after this layout was saved takes its default column.
  const added = order.length ? NEW_RAIL_WIDGETS.filter((id) => !order.includes(id)) : [];
  return {
    order: [...order, ...DASHBOARD_WIDGETS.filter((id) => !order.includes(id))],
    hidden,
    rail: Array.isArray(value?.rail) ? [...new Set([...clean(value.rail), ...added])] : [...DEFAULT_RAIL],
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

export function setWidgetHidden(preferences, id, hidden) {
  const next = normalizeDashboardPreferences(preferences);
  if (!DASHBOARD_WIDGETS.includes(id) || (hidden && isLockedWidget(id))) return next;
  next.hidden = hidden ? [...new Set([...next.hidden, id])] : next.hidden.filter((key) => key !== id);
  return next;
}

// The board width (its content box) from which CSS draws three tiles across; see
// the `@container board` rule in dashboard.css.
export const THREE_ACROSS_MIN_WIDTH = 1060;

// The columns the dashboard draws: visible widgets only, in order. A side rail
// with no main column beside it is drawn as the main column, so a layout never
// stretches a narrow rail across the whole page.
export function dashboardColumns(preferences, boardWidth = 0) {
  const { order, hidden, rail } = normalizeDashboardPreferences(preferences);
  const visible = order.filter((id) => !hidden.includes(id));
  let main = visible.filter((id) => !rail.includes(id));
  let side = visible.filter((id) => rail.includes(id));
  if (!main.length) [main, side] = [side, []];
  // The main column leads, so it must neither end above the side column nor far
  // below it. Two tiles wide it would, so it is cut one wide when the side column
  // has more tiles than it has rows (the two split the board in half), and three
  // wide when it has two rows or more to spare and the board is wide enough.
  const twoWideRows = Math.ceil(main.length / 2);
  let across = 2;
  if (side.length && twoWideRows < side.length) across = 1;
  else if (side.length && main.length >= 5 && twoWideRows - side.length >= 2 && boardWidth >= THREE_ACROSS_MIN_WIDTH) across = 3;
  return [['main', main], ['rail', side]].filter(([, ids]) => ids.length).map(([column, ids]) => {
    const wide = column === 'main' ? across : 1;
    const rows = Math.ceil(ids.length / wide);
    const wideLast = wide > 1 && ids.length % 2 === 1;
    return {
      column,
      ids,
      rows,
      across: wide,
      // Three across, how many columns a short last row's final tile covers.
      lastSpan: wide === 3 && ids.length % 3 ? 4 - (ids.length % 3) : 1,
      // One or two rows: the board stays as tall as its content instead of
      // stretching its tiles to fill the screen.
      fewRows: wide > 1 && rows < 3,
      wideLast,
      teamFooter: wideLast && ids.length >= 3 && ids.at(-1) === 'team',
    };
  });
}
