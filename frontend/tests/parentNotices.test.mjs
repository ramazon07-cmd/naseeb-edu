// Parent bell (card 45): built from the parent portal payload.
import test from 'node:test';
import assert from 'node:assert/strict';
import { parentNotices } from '../src/lib/notifications.js';

const now = new Date('2026-10-11T09:00:00Z');
const inDays = (days) => new Date(now.getTime() + days * 86400000).toISOString();
const child = (id, overrides = {}) => ({
  profile: { id, name: `Child ${id}` },
  tasks: [
    { id: id * 10, title: 'Late essay', status: 'todo', is_overdue: true, due_date: '2026-10-01' },
    { id: id * 10 + 1, title: 'Approved essay', status: 'approved', is_overdue: true, due_date: '2026-10-01' },
    { id: id * 10 + 2, title: 'Next week', status: 'todo', is_overdue: false, due_date: '2026-10-20' },
  ],
  meetings: [
    { id: id * 10, topic: 'Check-in', status: 'approved', starts_at: inDays(2) },
    { id: id * 10 + 1, topic: 'Far away', status: 'approved', starts_at: inDays(12) },
    { id: id * 10 + 2, topic: 'Cancelled', status: 'cancelled', starts_at: inDays(1) },
  ],
  ...overrides,
});

test('lists invitations, overdue open tasks and meetings in the next 7 days', () => {
  const notices = parentNotices({ pending_invitations: [{ id: 5, student_name: 'Aziz' }], children: [child(1)] }, now);
  assert.deepEqual(notices.map((item) => [item.kind, item.title, item.childId]), [
    ['invitation', 'Aziz', null], ['task', 'Late essay', 1], ['meeting', 'Check-in', 1],
  ]);
});

test('nothing pending means an empty bell', () => {
  assert.deepEqual(parentNotices({ pending_invitations: [], children: [child(2, { tasks: [], meetings: [] })] }, now), []);
  assert.deepEqual(parentNotices(undefined, now), []);
});
