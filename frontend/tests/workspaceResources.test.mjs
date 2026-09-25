import test from 'node:test';
import assert from 'node:assert/strict';
import { PAGED_ENDPOINTS, loadsDashboardStats, pagedListsAfter, resourcesFor, usesPagedLists, waitsBeforeLoading } from '../src/lib/workspaceResources.js';
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

test('the admin keeps only the counselor roster, not every account', () => {
  assert.deepEqual(resourcesFor({ role: 'admin' }).find(([key]) => key === 'accounts'), ['accounts', 'users/accounts', '?role=counselor']);
  assert.ok(!resourcesFor({ role: 'admin' }).some(([key]) => key === 'supportTickets'));
});

test('students and parents keep their own bounded collections in memory', () => {
  const student = resourcesFor({ role: 'student' }).map(([key]) => key);
  for (const key of ['students', 'tasks', 'applications', 'documents', 'roadmapMissions', 'supportTickets']) assert.ok(student.includes(key), key);
  assert.deepEqual(resourcesFor({ role: 'parent' }), [['parentPortal', 'parent-portal']]);
  assert.equal(usesPagedLists({ role: 'student' }), false);
  assert.equal(usesPagedLists({ role: 'parent' }), false);
  for (const role of ROLES) assert.ok(resourcesFor({ role }).every(([key, endpoint]) => key && endpoint), role);
});

test('a superuser with a student role gets the paged admin workspace', () => {
  const superuser = { role: 'student', is_superuser: true };
  assert.equal(usesPagedLists(superuser), true);
  assert.deepEqual(resourcesFor(superuser), resourcesFor({ role: 'admin' }));
});

test('dashboard stats load for everyone but parents', () => {
  assert.equal(loadsDashboardStats({ role: 'parent' }), false);
  assert.equal(loadsDashboardStats({ role: 'student' }), true);
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
