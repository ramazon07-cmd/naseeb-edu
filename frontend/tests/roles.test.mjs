import test from 'node:test';
import assert from 'node:assert/strict';
import { canDownloadCv, canManageWorkspaces, hasStaffTier, isCounselor, isPlatformAdmin, isSuperAdmin, isTaskManager, workspaceRole } from '../src/lib/roles.js';
import { resourcesFor } from '../src/lib/workspaceResources.js';

test('admins and superusers of any role are platform admins', () => {
  assert.equal(isPlatformAdmin({ role: 'admin' }), true);
  assert.equal(isPlatformAdmin({ role: 'student', is_superuser: true }), true);
  assert.equal(isPlatformAdmin({ role: 'counselor', is_superuser: false }), false);
  assert.equal(isPlatformAdmin(null), false);
});

test('platform admins inherit counselor and task-manager access', () => {
  const superuser = { role: 'student', is_superuser: true };
  assert.equal(isCounselor(superuser), true);
  assert.equal(isTaskManager(superuser), true);
  assert.equal(isCounselor({ role: 'teacher' }), false);
  assert.equal(isTaskManager({ role: 'teacher' }), true);
});

test('a superuser loads the admin workspace whatever its stored role', () => {
  const superuser = { role: 'student', is_superuser: true };
  assert.equal(workspaceRole(superuser), 'admin');
  assert.deepEqual(resourcesFor(superuser), resourcesFor({ role: 'admin' }));
  assert.equal(workspaceRole({ role: 'parent' }), 'parent');
});

test('the CV button shows for every staff role the CV endpoint lets in', () => {
  for (const role of ['counselor', 'admin', 'teacher', 'organization']) assert.equal(canDownloadCv({ role }), true, role);
  for (const role of ['student', 'parent', undefined]) assert.equal(canDownloadCv(role ? { role } : null), false, String(role));
  assert.equal(canDownloadCv({ role: 'student', is_superuser: true }), isPlatformAdmin({ role: 'student', is_superuser: true }));
});

test('staff tiers rank support < ops < superadmin, and only staff have one', () => {
  const support = { role: 'admin', staff_tier: 'support' };
  const ops = { role: 'admin', staff_tier: 'ops' };
  const superadmin = { role: 'admin', staff_tier: 'superadmin' };
  assert.deepEqual([support, ops, superadmin].map((user) => hasStaffTier(user, 'support')), [true, true, true]);
  assert.deepEqual([support, ops, superadmin].map(canManageWorkspaces), [false, true, true]);
  assert.deepEqual([support, ops, superadmin].map(isSuperAdmin), [false, false, true]);
  // Accounts from before tiers existed, and superusers, keep full access.
  assert.equal(isSuperAdmin({ role: 'admin' }), true);
  assert.equal(isSuperAdmin({ role: 'student', is_superuser: true, staff_tier: 'superadmin' }), true);
  for (const role of ['counselor', 'teacher', 'organization', 'student', 'parent']) {
    assert.equal(hasStaffTier({ role, staff_tier: 'superadmin' }, 'support'), false, role);
  }
});
