import test from 'node:test';
import assert from 'node:assert/strict';
import { taskPriorities } from '../src/dashboardPriorities.js';

test('submitted and approved tasks never become the next action', () => {
  const tasks = [
    { id: 1, status: 'approved', due_date: '2026-01-01' },
    { id: 2, status: 'submitted', due_date: '2026-01-01' },
    { id: 3, status: 'todo', due_date: '2026-09-08' },
  ];
  const result = taskPriorities(tasks, new Date(2026, 8, 6));
  assert.deepEqual(result.actionable.map(t => t.id), [3]);
  assert.deepEqual(result.reviewing.map(t => t.id), [2]);
  assert.equal(result.overdue.length, 0);
});

test('overdue work comes first, then deadline and urgency, without mutating API data', () => {
  const tasks = [
    { id: 1, status: 'todo', due_date: '2026-09-09', priority: 'urgent' },
    { id: 2, status: 'todo', due_date: '2026-09-06', priority: 'low' },
    { id: 3, status: 'todo', due_date: '2026-09-06', priority: 'high' },
    { id: 4, status: 'todo', due_date: '2026-09-05', priority: 'low' },
    { id: 5, status: 'todo' },
  ];
  const result = taskPriorities(tasks, new Date(2026, 8, 6, 0, 1));
  assert.deepEqual(result.actionable.map(t => t.id), [4, 3, 2, 1, 5]);
  assert.deepEqual(result.overdue.map(t => t.id), [4]);
  assert.deepEqual(tasks.map(t => t.id), [1, 2, 3, 4, 5]);
});
