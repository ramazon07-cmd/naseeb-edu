import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadsDashboardStats, resourcesFor } from '../src/lib/workspaceResources.js';
import { navigationFor, reachablePages } from '../src/lib/routes.js';

// The backend gives parents no school: they read their own portal and their direct
// chats with their children's counselors (card 15), never bookings, student lists or school accounts.
const PARENT_ENDPOINTS = new Set(['parent-portal', 'message-channels']);

test('parents load only the parent portal', () => {
  const endpoints = resourcesFor({ role: 'parent' }).map(([, endpoint]) => endpoint);
  assert.deepEqual(endpoints.filter((endpoint) => !PARENT_ENDPOINTS.has(endpoint)), []);
  assert.equal(loadsDashboardStats({ role: 'parent' }), false);
});

test('parent navigation has direct messages but no school pages', () => {
  const parent = { role: 'parent' };
  const reachable = reachablePages(parent);
  assert.ok(navigationFor(parent).includes('messages'));
  for (const page of ['bookings', 'students', 'screen_time', 'support']) {
    assert.ok(!navigationFor(parent).includes(page), `parents must not see ${page}`);
    assert.ok(!reachable.has(page), `parents must not reach ${page}`);
  }
});

test('only product admins are offered student deactivation', () => {
  const page = readFileSync(new URL('../src/pages/StudentsPage.jsx', import.meta.url), 'utf8');
  // And among them only the ops tier and above (support staff read and reset logins).
  assert.match(page, /onDeactivate=\{isPlatformAdmin\(user\) && !staffReadOnly \? deactivate : undefined\}/);
  assert.match(page, /const staffReadOnly = isPlatformAdmin\(user\) && !canManageWorkspaces\(user\);/);
});
