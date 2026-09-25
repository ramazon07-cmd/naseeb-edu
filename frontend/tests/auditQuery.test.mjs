import test from 'node:test';
import assert from 'node:assert/strict';
import { auditFilters } from '../src/lib/auditQuery.js';
import { listQuery } from '../src/lib/pagedList.js';

test('audit filters keep only filled, known keys', () => {
  assert.deepEqual(auditFilters({}), {});
  assert.deepEqual(
    auditFilters({ action: ' student_360 ', actor: '', school: 4, date_from: '2026-09-01', ignored: 'x' }),
    { action: 'student_360', school: '4', date_from: '2026-09-01' },
  );
});

test('audit filters ride on the shared paged-list query', () => {
  const query = new URLSearchParams(listQuery({ filters: auditFilters({ school: 4, date_to: '2026-09-02' }), ordering: '-created', pageSize: 50 }).slice(1));
  assert.equal(query.get('cursor'), '');
  assert.equal(query.get('school'), '4');
  assert.equal(query.get('date_to'), '2026-09-02');
  assert.equal(query.get('ordering'), '-created');
  assert.equal(query.has('actor'), false);
});
