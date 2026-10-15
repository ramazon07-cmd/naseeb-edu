import test from 'node:test';
import assert from 'node:assert/strict';
import { createResourceFreshness, STUDENT_REFRESH_MS } from '../src/lib/workspaceFreshness.js';
import { resourceDisplayState, studentPrimaryKeys } from '../src/lib/resourceState.js';
import { essayWorkspaceKeys, createMutationTracker, UNTRACKED_ENDPOINTS } from '../src/lib/reloadPlan.js';
import { pageLoadState } from '../src/lib/pageLoadState.js';
import { studentPageKeys } from '../src/lib/workspaceResources.js';
import { createAccountLayoutController } from '../src/lib/accountLayoutController.js';
import { normalizeDashboardPreferences } from '../src/dashboardPreferences.js';
import { hasPendingLayout, readCachedLayout, writeCachedLayout, syncDashboardLayout } from '../src/dashboardLayoutSync.js';

function storage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}
const old = normalizeDashboardPreferences({ order: ['tasks', 'team'], hidden: ['meetings'] });
const chosen = normalizeDashboardPreferences({ order: ['team', 'tasks'], hidden: ['programs'] });
const newest = normalizeDashboardPreferences({ order: ['applications', 'team'], hidden: ['screen_time'] });

test('failed first reads never become zero/complete states, but successful empty reads do', () => {
  assert.equal(resourceDisplayState(), 'loading');
  assert.equal(resourceDisplayState({ status: 'error', loaded: false }), 'error');
  assert.equal(resourceDisplayState({ status: 'success', loaded: true }), 'ready');
  assert.equal(resourceDisplayState({ status: 'error', loaded: true }), 'stale');
  for (const page of ['dashboard', 'roadmap', 'student_center']) {
    const keys = studentPageKeys(page);
    const statuses = Object.fromEntries(keys.map((key) => [key, { status: 'success', loaded: true }]));
    statuses.students = { status: 'error', loaded: false, error: 'Server error' };
    const state = pageLoadState({ keys, data: {}, resourceStatus: statuses, lazy: true, primaryKeys: studentPrimaryKeys(page) });
    assert.equal(state.contentBlocked, true, page);
  }
});

test('profile failure does not block account security or independent student tools', () => {
  for (const page of ['account_settings', 'essay_lab', 'messages', 'screen_time', 'find_personality']) {
    assert.deepEqual(studentPrimaryKeys(page), [], page);
  }
  for (const page of ['college_search', 'applications']) assert.deepEqual(studentPrimaryKeys(page), ['students', 'applications']);
});

test('page revisits and focus revalidate after the TTL, deduplicating active requests', () => {
  let now = 100;
  const freshness = createResourceFreshness({ now: () => now });
  assert.deepEqual(freshness.due(['students', 'tasks']), ['students', 'tasks']);
  const finish = freshness.begin(['students', 'tasks']);
  assert.deepEqual(freshness.due(['students', 'tasks'], { force: true }), []);
  finish('students', true); finish('tasks', true);
  assert.deepEqual(freshness.due(['students', 'tasks']), []);
  now += STUDENT_REFRESH_MS;
  assert.deepEqual(freshness.due(['students', 'tasks']), ['students', 'tasks']);
  const refresh = freshness.begin(['tasks']);
  refresh('tasks', false);
  assert.deepEqual(freshness.due(['tasks']), [], 'focus must not hammer a failed endpoint');
  now += STUDENT_REFRESH_MS;
  assert.deepEqual(freshness.due(['tasks']), ['tasks']);
});

test('an Essay Lab write during a read cannot be erased by the older read completing', () => {
  const freshness = createResourceFreshness();
  const settle = freshness.begin(['essays']);
  freshness.invalidate(essayWorkspaceKeys('/essay-lab/essays/8/trash/'));
  assert.deepEqual(freshness.due(['essays']), [], 'join the pending read instead of duplicating it');
  settle('essays', true);
  assert.deepEqual(freshness.due(['essays']), ['essays'], 'a response requested before the write remains stale');
  freshness.begin(['essays'])('essays', true);
  assert.deepEqual(freshness.due(['essays']), []);
  freshness.clear();
  assert.deepEqual(freshness.due(['essays']), ['essays'], 'another account starts with no cached freshness');
});

test('Essay Lab collection/metadata writes invalidate summaries, autosaves and folders do not', () => {
  const tracker = createMutationTracker(UNTRACKED_ENDPOINTS);
  for (const path of ['/essay-lab/essays/', '/essay-lab/essays/8/', '/essay-lab/essays/8/trash/', '/essay-lab/essays/8/restore/', '/essay-lab/essays/8/duplicate/', '/essay-lab/essays/8/share/', '/essay-lab/essays/8/unshare/']) {
    assert.deepEqual(essayWorkspaceKeys(path), ['essays'], path);
    tracker.note(path);
  }
  assert.deepEqual(tracker.take(), ['essays']);
  for (const path of ['/essay-lab/essays/8/autosave/', '/essay-lab/essays/8/tabs/', '/essay-lab/essays/8/depth-check/', '/essay-lab/folders/']) {
    assert.deepEqual(essayWorkspaceKeys(path), [], path);
    tracker.note(path);
  }
  assert.deepEqual(tracker.take(), []);
});

test('a slow initial account GET cannot undo a newer saved layout or notify listeners with the old layout', async () => {
  const cache = storage(), get = deferred(), events = [];
  const controller = createAccountLayoutController({ storage: cache, fetchLayout: () => get.promise, saveLayout: async () => {} });
  controller.subscribe(1, (event) => events.push(event));
  const loading = controller.load(1);
  assert.equal((await controller.save(1, chosen)).synced, true);
  get.resolve({ layout: old });
  assert.deepEqual(await loading, chosen);
  assert.deepEqual(readCachedLayout(cache, 1), chosen);
  assert.ok(events.every((event) => event.layout === chosen));
});

test('failed pending upload is retried on the next visit even when GET succeeded', async () => {
  const cache = storage();
  writeCachedLayout(cache, 1, chosen, { pending: true });
  let attempts = 0, broken = true;
  const controller = createAccountLayoutController({
    storage: cache, fetchLayout: async () => ({ layout: old }),
    saveLayout: async () => { attempts++; if (broken) throw new Error('offline'); },
  });
  assert.deepEqual(await controller.load(1), chosen);
  assert.equal(controller.isPending(1), true);
  assert.equal(hasPendingLayout(cache, 1), true);
  broken = false;
  assert.deepEqual(await controller.load(1), chosen);
  assert.equal(attempts, 2);
  assert.equal(controller.isPending(1), false);
  assert.equal(hasPendingLayout(cache, 1), false);
});

test('readable server and failed upload are separate sync results', async () => {
  const cache = storage();
  writeCachedLayout(cache, 1, chosen, { pending: true });
  const result = await syncDashboardLayout({ storage: cache, userId: 1, fetchLayout: async () => ({ layout: old }), saveLayout: async () => { throw new Error('write failed'); } });
  assert.equal(result.online, true);
  assert.equal(result.synced, false);
});

test('concurrent saves are serialized and an old completion cannot clear the newest pending choice', async () => {
  const cache = storage(), firstWrite = deferred(), started = deferred(), writes = [];
  const controller = createAccountLayoutController({
    storage: cache, fetchLayout: async () => ({ layout: old }),
    saveLayout: async (layout) => { writes.push(layout); if (writes.length === 1) { started.resolve(); await firstWrite.promise; } },
  });
  const first = controller.save(1, chosen);
  await started.promise;
  const second = controller.save(1, newest);
  assert.deepEqual(readCachedLayout(cache, 1), newest);
  assert.equal(hasPendingLayout(cache, 1), true);
  assert.equal(writes.length, 1);
  firstWrite.resolve();
  await Promise.all([first, second]);
  assert.deepEqual(writes, [chosen, newest]);
  assert.deepEqual(readCachedLayout(cache, 1), newest);
  assert.equal(hasPendingLayout(cache, 1), false);
});

test('blocked browser storage still preserves and retries the latest choice in this session', async () => {
  const brokenStorage = () => { throw new Error('storage blocked'); };
  let offline = true, saved;
  const controller = createAccountLayoutController({
    storage: brokenStorage, fetchLayout: async () => ({ layout: old }),
    saveLayout: async (layout) => { if (offline) throw new Error('offline'); saved = layout; },
  });
  assert.equal((await controller.save(1, chosen)).synced, false);
  offline = false;
  assert.deepEqual(await controller.load(1), chosen);
  assert.deepEqual(saved, chosen);
  assert.equal(controller.isPending(1), false);
});

test('sign-out invalidates a layout read before it can repopulate the cleared cache', async () => {
  const cache = storage(), get = deferred();
  const controller = createAccountLayoutController({ storage: cache, fetchLayout: () => get.promise, saveLayout: async () => {} });
  const pending = controller.load(1);
  controller.clear();
  get.resolve({ layout: old });
  await pending;
  assert.equal(readCachedLayout(cache, 1), null);
});
