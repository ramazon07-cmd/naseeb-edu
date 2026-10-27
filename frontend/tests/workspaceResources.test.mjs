import test from 'node:test';
import assert from 'node:assert/strict';
import { BOOKING_WINDOW_DAYS, PAGED_ENDPOINTS, bookingWindowStart, createInFlight, failedStatsStatus, loadsDashboardStats, mergeStats, pagedListsAfter, resourcesFor, usesPagedLists, waitsBeforeLoading } from '../src/lib/workspaceResources.js';
import { planWorkspaceReload } from '../src/lib/reloadPlan.js';

const ROLES = ['parent', 'organization', 'teacher', 'admin', 'counselor', 'student'];
// Collections that grow with the number of students on the platform.
const STAFF_WIDE = ['students', 'tasks', 'applications', 'documents', 'essays', 'achievements', 'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations', 'roadmap-missions', 'users/audit-events'];

test('staff roles never load a staff-wide collection into memory', () => {
  for (const role of ['organization', 'teacher', 'admin', 'counselor']) {
    const endpoints = resourcesFor({ role }).map(([, endpoint]) => endpoint);
    for (const endpoint of STAFF_WIDE) assert.ok(!endpoints.includes(endpoint), `${role} loads ${endpoint}`);
    assert.equal(usesPagedLists({ role }), true, role);
  }
});

test('the admin loads no school or account list at sign-in', () => {
  // Admin Control reads /api/admin/summary/; schools and counselors are paged and searched.
  const keys = resourcesFor({ role: 'admin' }).map(([key]) => key);
  for (const key of ['schools', 'accounts']) assert.ok(!keys.includes(key), key);
  assert.ok(!resourcesFor({ role: 'admin' }).some(([key]) => key === 'supportTickets'));
});

test('students and parents keep their own bounded collections in memory', () => {
  const student = resourcesFor({ role: 'student' }).map(([key]) => key);
  for (const key of ['students', 'tasks', 'applications', 'documents', 'supportTickets']) assert.ok(student.includes(key), key);
  assert.deepEqual(resourcesFor({ role: 'parent' }), [['parentPortal', 'parent-portal'], ['messageChannels', 'message-channels']]);
  assert.equal(usesPagedLists({ role: 'student' }), false);
  assert.equal(usesPagedLists({ role: 'parent' }), false);
  for (const role of ROLES) assert.ok(resourcesFor({ role }).every(([key, endpoint]) => key && endpoint), role);
});

test('a superuser with a student role gets the paged admin workspace', () => {
  const superuser = { role: 'student', is_superuser: true };
  assert.equal(usesPagedLists(superuser), true);
  assert.deepEqual(resourcesFor(superuser), resourcesFor({ role: 'admin' }));
});

test('dashboard stats load for staff only', () => {
  assert.equal(loadsDashboardStats({ role: 'parent' }), false);
  // The student dashboard reads its numbers from the student record.
  assert.equal(loadsDashboardStats({ role: 'student' }), false);
  assert.equal(loadsDashboardStats({ role: 'student', is_superuser: true }), true);
  for (const role of ['counselor', 'teacher', 'organization', 'admin']) assert.equal(loadsDashboardStats({ role }), true, role);
});

test('a save to a paged-only endpoint refreshes stats, not the whole workspace', () => {
  const counselor = resourcesFor({ role: 'counselor' });
  assert.deepEqual(planWorkspaceReload(['tasks'], counselor, ['dashboard', 'students'], PAGED_ENDPOINTS), ['dashboard']);
  assert.deepEqual(planWorkspaceReload(['tasks', 'bookings'], counselor, ['dashboard'], PAGED_ENDPOINTS).sort(), ['bookings', 'dashboard']);
  // Unknown writes still reload everything.
  assert.equal(planWorkspaceReload(['something-new'], counselor, ['dashboard'], PAGED_ENDPOINTS), null);
  // Students keep the old behaviour: their tasks are in memory.
  const student = resourcesFor({ role: 'student' });
  assert.deepEqual(planWorkspaceReload(['tasks'], student, ['dashboard', 'students'], PAGED_ENDPOINTS).sort(), ['dashboard', 'students', 'tasks']);
});

test('a plan change refreshes the paged school cards', () => {
  assert.deepEqual(pagedListsAfter([]), []);
  assert.deepEqual(pagedListsAfter(['tasks']), ['tasks', 'students']);
  assert.deepEqual(pagedListsAfter(['users/workspace-subscriptions']), ['users/workspace-subscriptions', 'schools', 'students']);
});

test('a superuser loads its workspace without student onboarding', () => {
  assert.equal(waitsBeforeLoading({ role: 'student', is_superuser: true, student_profile_complete: false }), false);
  assert.equal(waitsBeforeLoading({ role: 'student', student_profile_complete: false }), true);
  assert.equal(waitsBeforeLoading({ role: 'counselor', must_change_password: true }), true);
  assert.equal(waitsBeforeLoading(null), true);
});

test('a plain stats response keeps the last Home block, marked stale', () => {
  const home = { today: '2026-10-11' };
  assert.deepEqual(mergeStats({ students_total: 1, home }, { students_total: 2 }), { students_total: 2, home, home_stale: true });
  const fresh = { students_total: 3, home: { today: '2026-10-12' } };
  assert.equal(mergeStats({ home }, fresh), fresh);
  assert.deepEqual(mergeStats(null, { students_total: 2 }), { students_total: 2 });
  assert.deepEqual(mergeStats({ students_total: 1 }, { students_total: 2 }), { students_total: 2 });
});

test('staff sign-in loads a window of meetings and the first page of chats and tickets', () => {
  const now = new Date(2026, 9, 11, 15, 0);
  assert.equal(BOOKING_WINDOW_DAYS, 30);
  assert.equal(bookingWindowStart(now), '2026-09-11');
  assert.equal(bookingWindowStart(new Date(2026, 0, 5)), '2025-12-06');
  for (const role of ['counselor', 'teacher', 'organization']) {
    const resources = resourcesFor({ role }, now);
    assert.deepEqual(resources.find(([key]) => key === 'bookings'), ['bookings', 'bookings', '?starts_from=2026-09-11'], role);
    assert.equal(resources.find(([key]) => key === 'messageChannels')[3]?.firstPage, true, role);
    const tickets = resources.find(([key]) => key === 'supportTickets');
    if (tickets) assert.equal(tickets[3]?.firstPage, true, role);
  }
  // A student's own collections are small and still load whole.
  assert.ok(resourcesFor({ role: 'student' }, now).every(([, , , options]) => !options?.firstPage));
});

test('a stats refresh joins the workspace load of the same stats instead of superseding it', async () => {
  const inFlight = createInFlight();
  let calls = 0;
  let resolve;
  const request = () => { calls += 1; return new Promise((done) => { resolve = done; }); };
  // Sign-in on Home: the workspace load asks for ?include=home...
  const load = inFlight.track('home', request());
  // ...and Home, mounting meanwhile, joins it rather than sending it again.
  const joined = inFlight.join('home');
  assert.equal(joined, load);
  assert.equal(inFlight.join('dashboard'), null);
  resolve({ home: {} });
  assert.deepEqual(await joined, { home: {} });
  assert.equal(calls, 1);
  // Once settled the next refresh asks the server again.
  await Promise.resolve();
  assert.equal(inFlight.join('home'), null);
});

test('a failed load fails every caller that joined it, then frees the key', async () => {
  const inFlight = createInFlight();
  const failure = Promise.reject(new Error('offline'));
  inFlight.track('home', failure);
  await assert.rejects(inFlight.join('home'), /offline/);
  await Promise.resolve();
  assert.equal(inFlight.join('home'), null);
  // A newer request for the key is not cleared by an older one settling.
  let finishOld;
  const old = inFlight.track('home', new Promise((done) => { finishOld = done; }));
  const newer = inFlight.track('home', new Promise(() => {}));
  finishOld();
  await old;
  assert.equal(inFlight.join('home'), newer);
  inFlight.clear();
  assert.equal(inFlight.join('home'), null);
});

test('a failed stats refresh never leaves the dashboard loading', () => {
  const error = { message: 'Server error' };
  assert.deepEqual(failedStatsStatus({ status: 'loading', error: '', loaded: false }, error), { status: 'error', error: 'Server error', loaded: false });
  assert.deepEqual(failedStatsStatus(undefined, {}), { status: 'error', error: 'Unable to load this section.', loaded: false });
  // Stats on screen stay up after a failed refresh.
  assert.deepEqual(failedStatsStatus({ status: 'loading', error: '', loaded: true }, error), { status: 'success', error: '', loaded: true });
});

test('a counselor assistant loads only their chats up front, never essays or letters', () => {
  const assistant = { role: 'assistant' };
  assert.deepEqual(resourcesFor(assistant).map(([key]) => key), ['messageChannels']);
  assert.equal(usesPagedLists(assistant), true);
  assert.equal(loadsDashboardStats(assistant), true);
});

// Closed modules must not send requests just because the workspace signed in.
test('closed roadmap collections are absent from student and counselor workspace loads', () => {
  for (const role of ['student', 'counselor', 'assistant']) {
    for (const [, endpoint] of resourcesFor({ role })) {
      assert.ok(!endpoint.includes('roadmap'), `${role}: ${endpoint}`);
    }
  }
  assert.ok(resourcesFor({ role: 'admin' }).some(([, endpoint]) => endpoint === 'counselor-roadmap-templates'));
});
