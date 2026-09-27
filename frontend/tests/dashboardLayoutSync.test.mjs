import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDashboardPreferences } from '../src/dashboardPreferences.js';
import {
  DASHBOARD_LAYOUT_CACHE, DASHBOARD_LAYOUT_PENDING, hasPendingLayout, planLayoutSync, readCachedLayout,
  saveDashboardLayout, syncDashboardLayout, writeCachedLayout,
} from '../src/dashboardLayoutSync.js';

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k), map };
}

const custom = normalizeDashboardPreferences({ order: ['team', 'tasks'], hidden: ['meetings'], rail: ['team'] });
const other = normalizeDashboardPreferences({ order: ['applications'], hidden: [], rail: [] });
const cacheKey = (id) => `${DASHBOARD_LAYOUT_CACHE}:${id}`;

function server(layout = null, { failFetch = false, failSave = false } = {}) {
  const calls = { saved: [] };
  return {
    calls,
    fetchLayout: async () => { if (failFetch) throw new Error('offline'); return { layout }; },
    saveLayout: async (value) => { if (failSave) throw new Error('offline'); calls.saved.push(value); layout = value; return { layout }; },
  };
}

test('plan: an unsent local change wins, then the account, then a one-time upload of the local copy', () => {
  assert.deepEqual(planLayoutSync({ server: other, local: custom, pending: true }), { layout: custom, upload: true });
  assert.deepEqual(planLayoutSync({ server: other, local: custom, pending: false }), { layout: other, upload: false });
  assert.deepEqual(planLayoutSync({ server: null, local: custom, pending: false }), { layout: custom, upload: true });
  assert.deepEqual(planLayoutSync({ server: null, local: null, pending: false }), { layout: null, upload: false });
});

test('the account layout replaces this browser\'s copy', async () => {
  const storage = memoryStorage({ [cacheKey(5)]: JSON.stringify(custom) });
  const api = server(other);
  const result = await syncDashboardLayout({ storage, userId: 5, ...api });
  assert.deepEqual(result, { layout: other, online: true });
  assert.deepEqual(readCachedLayout(storage, 5), other);
  assert.equal(api.calls.saved.length, 0);
});

test('a layout saved before server sync is uploaded once', async () => {
  const storage = memoryStorage({ [cacheKey(5)]: JSON.stringify(custom) });
  const api = server(null);
  const first = await syncDashboardLayout({ storage, userId: 5, ...api });
  assert.deepEqual(first.layout, custom);
  assert.deepEqual(api.calls.saved, [custom]);
  await syncDashboardLayout({ storage, userId: 5, ...api });
  assert.equal(api.calls.saved.length, 1, 'the account has it now, so nothing is uploaded again');
});

test('no layout anywhere gives the default and uploads nothing', async () => {
  const storage = memoryStorage();
  const api = server(null);
  const result = await syncDashboardLayout({ storage, userId: 5, ...api });
  assert.deepEqual(result.layout, normalizeDashboardPreferences());
  assert.equal(api.calls.saved.length, 0);
});

test('offline: the cached layout is used and the account is asked again later', async () => {
  const storage = memoryStorage({ [cacheKey(5)]: JSON.stringify(custom) });
  const result = await syncDashboardLayout({ storage, userId: 5, ...server(other, { failFetch: true }) });
  assert.deepEqual(result, { layout: custom, online: false });
});

test('saving caches first; an unsent save is uploaded at the next sync', async () => {
  const storage = memoryStorage();
  const offline = server(other, { failSave: true });
  const saved = await saveDashboardLayout({ storage, userId: 5, layout: custom, saveLayout: offline.saveLayout });
  assert.deepEqual(saved, { synced: false, cached: true });
  assert.ok(hasPendingLayout(storage, 5));
  assert.deepEqual(readCachedLayout(storage, 5), custom);

  const online = server(other);
  const result = await syncDashboardLayout({ storage, userId: 5, ...online });
  assert.deepEqual(result.layout, custom, 'the newer local change beats the older account layout');
  assert.deepEqual(online.calls.saved, [custom]);
  assert.ok(!hasPendingLayout(storage, 5));
});

test('a successful save clears the pending mark', async () => {
  const storage = memoryStorage();
  const api = server(null);
  assert.deepEqual(await saveDashboardLayout({ storage, userId: 5, layout: custom, saveLayout: api.saveLayout }), { synced: true, cached: true });
  assert.ok(!storage.map.has(`${DASHBOARD_LAYOUT_PENDING}:5`));
});

test('layouts are per user and broken storage is tolerated', async () => {
  const storage = memoryStorage();
  writeCachedLayout(storage, 1, custom);
  assert.equal(readCachedLayout(storage, 2), null);
  storage.setItem(cacheKey(3), '{not json');
  assert.equal(readCachedLayout(storage, 3), null);
  storage.setItem(cacheKey(4), '[1,2]');
  assert.equal(readCachedLayout(storage, 4), null);
  const broken = () => { throw new Error('SecurityError'); };
  assert.equal(readCachedLayout(broken, 1), null);
  assert.equal(writeCachedLayout(broken, 1, custom), false);
  const api = server(null);
  assert.deepEqual(await saveDashboardLayout({ storage: broken, userId: 1, layout: custom, saveLayout: api.saveLayout }), { synced: true, cached: false });
});
