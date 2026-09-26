import test from 'node:test';
import assert from 'node:assert/strict';
import { seatUsage, subscriptionPayload } from '../src/lib/workspacePlan.js';
import { canManageWorkspaces, hasStaffTier } from '../src/lib/roles.js';

test('seat usage marks full and over-limit plans and treats null as unlimited', () => {
  const rows = seatUsage({
    seat_usage: { max_counselors: 4, max_students: 10, max_teachers: 0 },
    subscription: { limits: { max_counselors: 3, max_students: null, max_teachers: 0 } },
  });
  assert.deepEqual(rows.map((row) => [row.key, row.used, row.limit, row.over, row.full]), [
    ['max_counselors', 4, 3, true, true],
    ['max_students', 10, null, false, false],
    ['max_teachers', 0, 0, false, true],
  ]);
  assert.deepEqual(seatUsage({ subscription: {} }), []);
});

test('cleared period dates are sent as null', () => {
  assert.deepEqual(subscriptionPayload({ plan: 'center', status: 'active', period_start: '', period_end: '2027-06-30' }), {
    plan: 'center', status: 'active', period_start: null, period_end: '2027-06-30',
  });
});

test('only ops and super admins manage workspaces', () => {
  assert.equal(canManageWorkspaces({ role: 'admin', staff_tier: 'support' }), false);
  assert.equal(canManageWorkspaces({ role: 'admin', staff_tier: 'ops' }), true);
  assert.equal(canManageWorkspaces({ role: 'admin', staff_tier: 'superadmin' }), true);
  assert.equal(canManageWorkspaces({ role: 'student', is_superuser: true, staff_tier: 'superadmin' }), true);
  assert.equal(canManageWorkspaces({ role: 'counselor' }), false);
  assert.equal(hasStaffTier({ role: 'admin', staff_tier: 'support' }, 'support'), true);
});
