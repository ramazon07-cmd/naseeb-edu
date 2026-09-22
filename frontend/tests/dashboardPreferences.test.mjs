import test from 'node:test';
import assert from 'node:assert/strict';
import { DASHBOARD_WIDGETS, normalizeDashboardPreferences, moveDashboardWidget } from '../src/dashboardPreferences.js';
test('invalid and old stored preferences preserve every supported card once', () => {
  assert.deepEqual(normalizeDashboardPreferences(null), { order: DASHBOARD_WIDGETS, hidden: [], rail: ['roadmap', 'discovery'] });
  const result = normalizeDashboardPreferences({order: ['team', 'removed', 'team'], hidden: ['removed', 'tasks', 'tasks']});
  assert.equal(result.order[0], 'team');
  assert.equal(new Set(result.order).size, DASHBOARD_WIDGETS.length);
  assert.deepEqual(result.hidden, ['tasks']);
});
test('a corrupted all-hidden preference cannot leave an empty dashboard', () => {
  const result = normalizeDashboardPreferences({hidden: DASHBOARD_WIDGETS});
  assert.equal(result.hidden.length, DASHBOARD_WIDGETS.length - 1);
});
test('saved card order and visibility survive a JSON roundtrip', () => {
  const value = {order: [...DASHBOARD_WIDGETS].reverse(), hidden: ['meetings', 'team'], rail: ['tasks']};
  assert.deepEqual(normalizeDashboardPreferences(JSON.parse(JSON.stringify(value))), value);
});

test('moves widgets across columns and inserts before a drop target', () => {
  const initial = normalizeDashboardPreferences({hidden: ['tasks']});
  const next = moveDashboardWidget(initial, 'tasks', 'rail', 'team');
  assert.ok(next.rail.includes('tasks'));
  assert.ok(!next.hidden.includes('tasks'));
  assert.equal(next.order.indexOf('tasks') + 1, next.order.indexOf('team'));
  assert.deepEqual(initial.hidden, ['tasks']);
  const back = moveDashboardWidget(next, 'tasks', 'main', 'journey');
  assert.ok(!back.rail.includes('tasks'));
  assert.equal(back.order[0], 'tasks');
});
test('migrates old layouts and cleans invalid column assignments', () => {
  assert.deepEqual(normalizeDashboardPreferences({order:['tasks']}).rail, ['roadmap', 'discovery']);
  assert.deepEqual(normalizeDashboardPreferences({rail:['team','team','gone']}).rail, ['team']);
  assert.deepEqual(normalizeDashboardPreferences({rail:[]}).rail, []);
});

test('upgrades the old default but preserves intentional custom arrangements', () => {
  const old = {order:['journey','tasks','meetings','applications','discovery','team'], hidden:[], rail:['discovery','team']};
  assert.deepEqual(normalizeDashboardPreferences(old), normalizeDashboardPreferences());
  const custom = normalizeDashboardPreferences({...old, hidden:['meetings']});
  assert.deepEqual(custom.hidden, ['meetings']);
  assert.deepEqual(custom.rail, ['discovery','team']);
  assert.ok(custom.order.includes('roadmap'));
});
