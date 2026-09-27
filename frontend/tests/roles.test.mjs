import test from 'node:test';
import assert from 'node:assert/strict';
import { isCounselor, isPlatformAdmin, isTaskManager, workspaceRole } from '../src/lib/roles.js';
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
