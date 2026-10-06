import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { STUDENT_AUTHORED_RECORDS, canDeleteStudentRecord } from '../src/lib/recordDeletes.js';

test('staff get no delete action on student-authored essays and portfolio records', () => {
  for (const role of ['counselor', 'admin', 'teacher', 'organization', 'parent']) {
    for (const resource of STUDENT_AUTHORED_RECORDS) assert.equal(canDeleteStudentRecord({ role }, resource), false, `${role} ${resource}`);
  }
  assert.equal(canDeleteStudentRecord({ role: 'counselor', is_superuser: true }, 'essays'), false);
});

test('the student keeps delete on their own work; other resources are unchanged', () => {
  for (const resource of STUDENT_AUTHORED_RECORDS) assert.equal(canDeleteStudentRecord({ role: 'student' }, resource), true);
  assert.equal(canDeleteStudentRecord({ role: 'counselor' }, 'applications'), true);
  assert.equal(canDeleteStudentRecord({ role: 'counselor' }, 'recommendations'), true);
});

test('the record list uses the rule for its delete button', () => {
  const source = readFileSync(new URL('../src/pages/ResourceSection.jsx', import.meta.url), 'utf8');
  assert.match(source, /allowCreate && canDeleteStudentRecord\(user, resource\)/);
});
