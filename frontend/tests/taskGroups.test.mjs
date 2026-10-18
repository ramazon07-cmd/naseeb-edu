import test from 'node:test';
import assert from 'node:assert/strict';
import { groupTasksByStudent, taskStatus } from '../src/lib/taskGroups.js';

const task = (id, student, status, due) => ({ id, student, student_name: `Student ${student}`, status, due_date: due });
const today = '2026-10-16';

test('a task still owed and past its date is late', () => {
  assert.equal(taskStatus(task(1, 1, 'todo', '2026-10-01'), today), 'late');
  assert.equal(taskStatus(task(1, 1, 'in_progress', '2026-10-16'), today), 'in_progress');
  assert.equal(taskStatus(task(1, 1, 'submitted', '2026-10-01'), today), 'submitted');
  assert.equal(taskStatus(task(1, 1, 'approved', '2026-10-01'), today), 'approved');
  assert.equal(taskStatus(task(1, 1, 'todo', null), today), 'todo');
});

test('students with late work come first, then work to review, then the nearest date', () => {
  const groups = groupTasksByStudent([
    task(1, 10, 'todo', '2026-11-01'),
    task(2, 20, 'submitted', '2026-12-01'),
    task(3, 30, 'todo', '2026-10-01'),
    task(4, 30, 'todo', '2026-09-01'),
    task(5, 40, 'todo', '2026-10-20'),
  ], today);
  assert.deepEqual(groups.map((group) => group.student), [30, 20, 40, 10]);
  assert.deepEqual(groups[0].tasks.map((item) => item.id), [4, 3]);
  assert.equal(groups[0].late, 2);
  assert.equal(groups[1].toReview, 1);
});

test('no tasks, no groups', () => {
  assert.deepEqual(groupTasksByStudent([], today), []);
});
