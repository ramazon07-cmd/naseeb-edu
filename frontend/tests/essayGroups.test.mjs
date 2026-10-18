import test from 'node:test';
import assert from 'node:assert/strict';
import { groupByStudent } from '../src/lib/essayGroups.js';

const essay = (id, student, status, updated) => ({ id, student, student_name: `Student ${student}`, status, updated_at: updated });

test('essays are grouped by student, waiting students first, then newest work', () => {
  const groups = groupByStudent([
    essay(1, 10, 'draft', '2026-10-16T09:00:00Z'),
    essay(2, 20, 'needs_revision', '2026-07-19T09:00:00Z'),
    essay(3, 10, 'reviewing', '2026-10-01T09:00:00Z'),
    essay(4, 30, 'approved', '2026-10-10T09:00:00Z'),
  ]);
  assert.deepEqual(groups.map((group) => group.student), [10, 30, 20]);
  assert.deepEqual(groups[0].essays.map((item) => item.id), [1, 3]);
  assert.equal(groups[0].waiting, true);
  assert.equal(groups[1].waiting, false);
  assert.equal(groups[0].latest, '2026-10-16T09:00:00Z');
});

test('no essays, no groups', () => {
  assert.deepEqual(groupByStudent([]), []);
});
