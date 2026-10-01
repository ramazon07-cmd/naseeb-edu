import test from 'node:test';
import assert from 'node:assert/strict';
import { DASHBOARD_WIDGETS, LOCKED_WIDGETS, dashboardColumns, isLockedWidget, moveDashboardWidget, normalizeDashboardPreferences, setWidgetHidden } from '../src/dashboardPreferences.js';
test('invalid and old stored preferences preserve every supported card once', () => {
  assert.deepEqual(normalizeDashboardPreferences(null), { order: DASHBOARD_WIDGETS, hidden: [], rail: ['roadmap', 'discovery', 'programs'] });
  const result = normalizeDashboardPreferences({order: ['team', 'removed', 'team'], hidden: ['removed', 'meetings', 'meetings']});
  assert.equal(result.order[0], 'team');
  assert.equal(new Set(result.order).size, DASHBOARD_WIDGETS.length);
  assert.deepEqual(result.hidden, ['meetings']);
});
test('the locked widgets cannot be hidden, whatever a saved layout says', () => {
  assert.deepEqual(LOCKED_WIDGETS, ['journey', 'tasks', 'applications', 'roadmap']);
  // A corrupted all-hidden layout, or one saved before the lock existed, still shows them.
  const result = normalizeDashboardPreferences({ hidden: DASHBOARD_WIDGETS });
  assert.deepEqual(result.hidden, DASHBOARD_WIDGETS.filter((id) => !isLockedWidget(id)));
  assert.ok(LOCKED_WIDGETS.every((id) => !result.hidden.includes(id)));
  assert.deepEqual(normalizeDashboardPreferences({ order: ['tasks'], hidden: ['tasks', 'team'] }).hidden, ['team']);
});
test('hiding skips locked widgets and never touches the input', () => {
  const initial = normalizeDashboardPreferences();
  assert.deepEqual(setWidgetHidden(initial, 'meetings', true).hidden, ['meetings']);
  assert.deepEqual(setWidgetHidden(setWidgetHidden(initial, 'meetings', true), 'meetings', false).hidden, []);
  for (const id of LOCKED_WIDGETS) assert.deepEqual(setWidgetHidden(initial, id, true).hidden, [], id);
  assert.deepEqual(setWidgetHidden(initial, 'nope', true).hidden, []);
  assert.deepEqual(initial.hidden, []);
});
test('saved card order and visibility survive a JSON roundtrip', () => {
  const value = {order: [...DASHBOARD_WIDGETS].reverse(), hidden: ['meetings', 'team'], rail: ['tasks']};
  assert.deepEqual(normalizeDashboardPreferences(JSON.parse(JSON.stringify(value))), value);
});

test('moves widgets across columns and inserts before a drop target', () => {
  const initial = normalizeDashboardPreferences({hidden: ['meetings']});
  const next = moveDashboardWidget(initial, 'meetings', 'rail', 'team');
  assert.ok(next.rail.includes('meetings'));
  assert.ok(!next.hidden.includes('meetings'));
  assert.equal(next.order.indexOf('meetings') + 1, next.order.indexOf('team'));
  assert.deepEqual(initial.hidden, ['meetings']);
  const back = moveDashboardWidget(next, 'meetings', 'main', 'journey');
  assert.ok(!back.rail.includes('meetings'));
  assert.equal(back.order[0], 'meetings');
});
test('migrates old layouts and cleans invalid column assignments', () => {
  assert.deepEqual(normalizeDashboardPreferences({order:['tasks']}).rail, ['roadmap', 'discovery', 'programs']);
  assert.deepEqual(normalizeDashboardPreferences({rail:['team','team','gone']}).rail, ['team']);
  assert.deepEqual(normalizeDashboardPreferences({rail:[]}).rail, []);
});

test('upgrades the old default but preserves intentional custom arrangements', () => {
  const old = {order:['journey','tasks','meetings','applications','discovery','team'], hidden:[], rail:['discovery','team']};
  assert.deepEqual(normalizeDashboardPreferences(old), normalizeDashboardPreferences());
  const custom = normalizeDashboardPreferences({...old, hidden:['meetings']});
  assert.deepEqual(custom.hidden, ['meetings']);
  // Its own rail is kept; widgets it never knew about join their default column.
  assert.deepEqual(custom.rail, ['discovery','team','programs']);
  assert.ok(custom.order.includes('roadmap'));
});

test('every layout draws each visible widget once, and the locked ones always', () => {
  const subsets = (ids) => Array.from({ length: 1 << ids.length }, (_, mask) => ids.filter((_, index) => mask & (1 << index)));
  let checked = 0;
  for (const hidden of subsets(DASHBOARD_WIDGETS)) {
    for (const rail of subsets(DASHBOARD_WIDGETS)) {
      const { order, hidden: kept } = normalizeDashboardPreferences({ order: [...DASHBOARD_WIDGETS].reverse(), hidden, rail });
      const columns = dashboardColumns({ order, hidden, rail });
      const drawn = columns.flatMap((column) => column.ids);
      assert.equal(new Set(drawn).size, drawn.length, 'no widget twice');
      assert.deepEqual([...drawn].sort(), order.filter((id) => !kept.includes(id)).sort());
      assert.ok(LOCKED_WIDGETS.every((id) => drawn.includes(id)), 'locked widgets are always drawn');
      // There is always a main column: a rail with nothing beside it is drawn as the main column.
      assert.equal(columns[0].column, 'main');
      assert.ok(columns.length <= 2 && (columns.length < 2 || columns[1].column === 'rail'));
      // The main column neither ends above the side one nor far below it: it is cut one or three tiles wide.
      const side = columns.length === 2 ? columns[1].ids.length : 0;
      const twoWideRows = Math.ceil(columns[0].ids.length / 2);
      const mainAcross = !side ? 2 : twoWideRows < side ? 1 : columns[0].ids.length >= 5 && twoWideRows - side >= 2 ? 3 : 2;
      for (const { column, ids, rows, across, lastSpan, fewRows, wideLast, teamFooter } of columns) {
        const wide = column === 'main' ? mainAcross : 1;
        assert.ok(ids.length > 0);
        assert.equal(across, wide);
        assert.equal(rows, Math.ceil(ids.length / wide));
        assert.equal(fewRows, wide > 1 && rows < 3);
        assert.equal(wideLast, wide > 1 && ids.length % 2 === 1);
        assert.equal(teamFooter, wideLast && ids.length >= 3 && ids.at(-1) === 'team');
        // Three across, the last tile fills what is left of a short last row.
        assert.equal(wide === 3 ? (ids.length % 3 || 3) - 1 + lastSpan : lastSpan, wide === 3 ? 3 : 1);
      }
      checked += 1;
    }
  }
  assert.equal(checked, 512 * 512);
});

test('the main column is cut one or three tiles wide so it matches the side column', () => {
  // Meetings, team and screen time hidden: three tiles beside three would leave a hole under a two-wide main column.
  const hidden = ['meetings', 'team', 'screen_time'];
  const [main, rail] = dashboardColumns({ hidden });
  assert.deepEqual([main.ids, main.across, main.wideLast, main.rows], [['journey', 'applications', 'tasks'], 1, false, 3]);
  assert.deepEqual([rail.ids, rail.across], [['roadmap', 'discovery', 'programs'], 1]);
  // Discovery and programs hidden: six beside one would leave the side column far short.
  const [six] = dashboardColumns({ hidden: ['discovery', 'programs'] });
  assert.deepEqual([six.ids.length, six.across, six.rows, six.lastSpan, six.fewRows], [6, 3, 2, 1, true]);
  const [five] = dashboardColumns({ hidden: ['discovery', 'programs', 'screen_time'] });
  assert.deepEqual([five.ids.length, five.across, five.rows, five.lastSpan, five.wideLast], [5, 3, 2, 2, true]);
  // The default layout (six beside three) and near matches keep two across.
  for (const layout of [{}, { hidden: ['programs'] }, { hidden: ['discovery'] }, { hidden: [...hidden, 'programs'] }]) assert.equal(dashboardColumns(layout)[0].across, 2);
});

test('a side rail with no main column beside it is drawn as the main column', () => {
  const [only] = dashboardColumns({ order: DASHBOARD_WIDGETS, hidden: ['meetings'], rail: DASHBOARD_WIDGETS });
  assert.equal(only.column, 'main');
  assert.equal(only.ids.length, DASHBOARD_WIDGETS.length - 1);
  const columns = dashboardColumns({});
  assert.deepEqual(columns.map((column) => [column.column, column.ids.length]), [['main', 6], ['rail', 3]]);
  assert.deepEqual(columns[1].ids, ['roadmap', 'discovery', 'programs']);
});
