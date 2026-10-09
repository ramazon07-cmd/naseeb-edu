import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  PAGED_ENDPOINTS, STUDENT_PAGE_KEYS, STUDENT_SHELL_KEYS, loadsDashboardStats, loadsLazily,
  missingKeys, resourcesFor, selectWorkspaceLoad, studentPageKeys,
} from '../src/lib/workspaceResources.js';
import { planWorkspaceReload } from '../src/lib/reloadPlan.js';
import { pageLoadState } from '../src/lib/pageLoadState.js';
import { navigationFor } from '../src/lib/routes.js';

const student = { id: 7, role: 'student', student_profile_complete: true };
const STAFF_ROLES = ['counselor', 'teacher', 'organization', 'admin', 'parent'];

// Mirrors hooks/useWorkspaceData: which endpoints a session fetches, in order.
function session(user) {
  const requested = new Set();
  const fetched = [];
  const load = (planned, options) => {
    const selected = selectWorkspaceLoad(user, planned, requested, options);
    selected.forEach(([key, endpoint]) => { requested.add(key); fetched.push(endpoint || 'dashboard/stats'); });
    return selected.map(([, endpoint]) => endpoint || 'dashboard/stats');
  };
  const ensure = (keys) => {
    const missing = missingKeys(user, keys, requested);
    return missing.length ? load(missing) : [];
  };
  return {
    requested, fetched, load, ensure,
    signIn: () => (loadsLazily(user) ? ensure(STUDENT_SHELL_KEYS) : load(null)),
    open: (page) => ensure(studentPageKeys(page)),
    reloadAfter: (written) => load(planWorkspaceReload(written, resourcesFor(user), ['dashboard', 'students'], PAGED_ENDPOINTS), { changed: true }),
  };
}

test('a student signing in to the dashboard fetches only what the dashboard shows', () => {
  const s = session(student);
  s.signIn();
  s.open('dashboard');
  assert.deepEqual(s.fetched.sort(), ['bookings', 'essays', 'program-services', 'student-team', 'students', 'support-tickets', 'tasks']);
  // The program catalog is large: the Programs tile fetches it on its own, so the dashboard never waits for it.
  assert.ok(!studentPageKeys('dashboard').includes('opportunityPrograms'));
  for (const endpoint of ['universities', 'scholarships', 'store-items', 'documents', 'message-channels', 'roadmap-missions', 'dashboard/stats']) {
    assert.ok(!s.fetched.includes(endpoint), `${endpoint} must wait for its page`);
  }
});

test('each student page fetches its own collections the first time it opens, once', () => {
  const s = session(student);
  s.signIn();
  s.open('dashboard');
  assert.deepEqual(s.open('programs'), ['opportunity-programs']);
  // College Search pages the university catalogue itself (/api/college-search/);
  // essays came with the dashboard, and the page adds what "What you need" counts.
  assert.deepEqual(s.open('college_search').sort(), ['applications', 'documents', 'recommendations', 'scholarships']);
  // Applications' collections came with College Search: nothing new to fetch.
  assert.deepEqual(s.open('applications'), []);
  assert.deepEqual(s.open('store'), ['store-items']);
  assert.deepEqual(s.open('messages'), ['message-channels']);
  assert.deepEqual(s.open('roadmap'), ['roadmap-missions']);
  // Revisiting any page (or StrictMode running the effect twice) refetches nothing.
  for (const page of Object.keys(STUDENT_PAGE_KEYS)) s.open(page);
  for (const page of Object.keys(STUDENT_PAGE_KEYS)) assert.deepEqual(s.open(page), [], page);
  assert.equal(new Set(s.fetched).size, s.fetched.length, 'no endpoint is fetched twice');
});

test('every student page lists its collections and every collection belongs to a page', () => {
  const keys = new Set(resourcesFor(student).map(([key]) => key));
  for (const page of navigationFor(student)) assert.ok(page in STUDENT_PAGE_KEYS, `${page} has no lazy-load entry`);
  const used = new Set([...STUDENT_SHELL_KEYS, ...Object.values(STUDENT_PAGE_KEYS).flat()]);
  for (const key of used) assert.ok(keys.has(key), `${key} is not a student collection`);
  // Anything never listed would stay unloaded until the search opens.
  for (const key of keys) assert.ok(used.has(key), `${key} is loaded by no student page`);
  for (const page of Object.keys(STUDENT_PAGE_KEYS)) assert.ok(studentPageKeys(page).includes('students'), page);
});

test('opening the search loads the collections pages have not yet, without repeats', () => {
  const s = session(student);
  s.signIn();
  s.open('dashboard');
  const before = s.fetched.length;
  s.ensure(resourcesFor(student).map(([key]) => key));
  assert.equal(s.fetched.length, resourcesFor(student).length);
  assert.ok(s.fetched.length > before);
  assert.equal(new Set(s.fetched).size, s.fetched.length);
});

test('a student save refetches only collections already loaded', () => {
  const s = session(student);
  s.signIn();
  s.open('dashboard');
  assert.deepEqual(s.reloadAfter(['tasks']).sort(), ['students', 'tasks']);
  // An application written from College Search before Applications ever
  // loaded (impossible in the UI, but the plan must not pull catalogues).
  assert.deepEqual(s.reloadAfter(['applications']), ['students']);
  // An unknown write refetches what is loaded, not every collection.
  assert.deepEqual(s.reloadAfter(['something-new']).sort(), ['bookings', 'essays', 'program-services', 'student-team', 'students', 'support-tickets', 'tasks']);
  // A retry of a named key always fetches it.
  assert.deepEqual(s.load(['scholarships']), ['scholarships']);
});

test('no role downloads the university catalogue at sign-in or with a page', () => {
  for (const role of ['student', ...STAFF_ROLES]) {
    assert.ok(!resourcesFor({ id: 1, role }).some(([, endpoint]) => endpoint === 'universities'), role);
  }
  assert.ok(!Object.values(STUDENT_PAGE_KEYS).flat().includes('universities'));
});

test('other roles still load their whole workspace at sign-in, exactly as before', () => {
  for (const role of STAFF_ROLES) {
    const user = { id: 1, role };
    assert.equal(loadsLazily(user), false, role);
    const s = session(user);
    s.signIn();
    const expected = [...(loadsDashboardStats(user) ? ['dashboard/stats'] : []), ...resourcesFor(user).map(([, endpoint]) => endpoint)];
    assert.deepEqual(s.fetched, expected, role);
    // Opening pages never fetches anything extra for them.
    for (const page of navigationFor(user)) assert.deepEqual(s.ensure(studentPageKeys(page)), [], `${role} ${page}`);
    assert.deepEqual(missingKeys(user, ['universities', 'tasks'], new Set()), [], role);
  }
  // Counselors and admins keep dashboard stats; a superuser with a student role is an admin.
  assert.equal(loadsDashboardStats({ role: 'counselor' }), true);
  assert.equal(loadsDashboardStats({ role: 'organization' }), true);
  assert.equal(loadsLazily({ role: 'student', is_superuser: true }), false);
});

test('a lazily loaded page shows a skeleton, not an empty list, until its data arrives', () => {
  const keys = studentPageKeys('programs');
  const data = { students: [{ id: 1 }], opportunityPrograms: [] };
  const loadedStudent = { students: { status: 'success', error: '', loaded: true } };
  // Opened, but the effect has not asked for the programs yet.
  assert.equal(pageLoadState({ keys, data, stats: null, loading: false, resourceStatus: loadedStudent, lazy: true }).initialLoading, true);
  // On its way.
  const pending = { ...loadedStudent, opportunityPrograms: { status: 'loading', error: '', loaded: false } };
  assert.equal(pageLoadState({ keys, data, stats: null, loading: true, resourceStatus: pending, lazy: true }).initialLoading, true);
  // Arrived empty: the page (and its own empty state) shows.
  const done = { ...loadedStudent, opportunityPrograms: { status: 'success', error: '', loaded: true } };
  assert.equal(pageLoadState({ keys, data, stats: null, loading: false, resourceStatus: done, lazy: true }).initialLoading, false);
  // A refresh after a save keeps the page mounted.
  const refreshing = { ...loadedStudent, opportunityPrograms: { status: 'loading', error: '', loaded: true } };
  const state = pageLoadState({ keys, data, stats: null, loading: true, resourceStatus: refreshing, lazy: true });
  assert.equal(state.initialLoading, false);
  assert.deepEqual(state.loadingKeys, ['opportunityPrograms']);
  // A failed load shows the page with its retry banner.
  const failed = { ...loadedStudent, opportunityPrograms: { status: 'error', error: 'x', loaded: false } };
  const error = pageLoadState({ keys, data, stats: null, loading: false, resourceStatus: failed, lazy: true });
  assert.equal(error.initialLoading, false);
  assert.deepEqual(error.failedKeys, ['opportunityPrograms']);
  // Without `lazy` the old rule holds: any visible data ends the skeleton.
  assert.equal(pageLoadState({ keys, data, stats: null, loading: true, resourceStatus: pending }).initialLoading, false);
});

test('the app starts students with the shell and loads pages as they open', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(app, /await loadData\(current\)/, 'sign-in goes through loadInitial');
  assert.match(app, /await loadInitial\(current\)/);
  assert.match(app, /ensureLoaded\(user, studentPageKeys\(page\)\)/);
});

for (const [page, dependencies] of [
  ['college_search', ['essays', 'documents', 'recommendations']],
  ['applications', ['essays', 'recommendations']],
]) {
  test(`${page} waits for each readiness dependency and blocks first-load failures`, () => {
    const s = session(student);
    s.signIn();
    const fetched = s.open(page);
    for (const dependency of dependencies) assert.ok(fetched.includes(dependency));
    const keys = studentPageKeys(page);
    const success = Object.fromEntries(keys.map((key) => [key, { status: 'success', loaded: true }]));
    const state = (resourceStatus) => pageLoadState({ keys, data: { students: [{ id: 1 }], universities: [{ id: 1 }] }, stats: null, loading: false, resourceStatus, lazy: true, requireComplete: true });
    for (const dependency of dependencies) {
      const absent = { ...success };
      delete absent[dependency];
      assert.equal(state(absent).initialLoading, true, dependency);
      assert.equal(state({ ...success, [dependency]: { status: 'loading', loaded: false } }).initialLoading, true, dependency);
      const failed = state({ ...success, [dependency]: { status: 'error', loaded: false, error: 'Failed' } });
      assert.equal(failed.contentBlocked, true, dependency);
      assert.deepEqual(failed.failedKeys, [dependency]);
      assert.equal(state({ ...success, [dependency]: { status: 'error', loaded: true, error: 'Failed refresh' } }).contentBlocked, false, dependency);
    }
    assert.equal(state(success).initialLoading, false);
    assert.equal(state(success).contentBlocked, false);
  });
}
