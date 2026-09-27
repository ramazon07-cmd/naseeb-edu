import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadsDashboardStats, resourcesFor } from '../src/lib/workspaceResources.js';
import { navigationFor, reachablePages } from '../src/lib/routes.js';

// The backend gives parents no school: they may read only their own portal
// and never messaging, bookings, student lists or school accounts.
const PARENT_ENDPOINTS = new Set(['parent-portal']);

test('parents load only the parent portal', () => {
  const endpoints = resourcesFor({ role: 'parent' }).map(([, endpoint]) => endpoint);
  assert.deepEqual(endpoints.filter((endpoint) => !PARENT_ENDPOINTS.has(endpoint)), []);
  assert.equal(loadsDashboardStats({ role: 'parent' }), false);
});

test('parent navigation has no messaging or school pages', () => {
  const parent = { role: 'parent' };
  const reachable = reachablePages(parent);
  for (const page of ['messages', 'bookings', 'students', 'screen_time', 'support']) {
    assert.ok(!navigationFor(parent).includes(page), `parents must not see ${page}`);
    assert.ok(!reachable.has(page), `parents must not reach ${page}`);
  }
});

test('only product admins are offered student deactivation', () => {
  const page = readFileSync(new URL('../src/pages/StudentsPage.jsx', import.meta.url), 'utf8');
  assert.match(page, /onDeactivate=\{isPlatformAdmin\(user\) \? deactivate : undefined\}/);
});
