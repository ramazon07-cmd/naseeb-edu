import test from 'node:test';
import assert from 'node:assert/strict';
import { buildIndex, matchesQuery, mergeSearchResults, remoteSearchEntries, searchIndex, searchText } from '../src/lib/searchIndex.js';

test('record text is computed once per object and matches like the old filter', () => {
  const item = { title: 'IELTS Upload', nested: { note: 'Deadline' } };
  const original = JSON.stringify;
  let calls = 0;
  JSON.stringify = (...args) => { calls += 1; return original(...args); };
  try {
    for (const q of ['i', 'ie', 'iel', 'ielts', 'deadline', 'x']) matchesQuery(item, q);
  } finally { JSON.stringify = original; }
  assert.equal(calls, 1);
  assert.equal(matchesQuery(item, 'IELTS'), true);
  assert.equal(matchesQuery(item, 'deadline'), true);
  assert.equal(matchesQuery(item, 'missing'), false);
  assert.equal(matchesQuery(item, ''), true);
  assert.equal(searchText(null), 'null');
});

test('a prebuilt index answers queries without rebuilding', () => {
  let built = 0;
  const index = buildIndex([{ id: 1, name: 'Tashkent Sprint' }, { id: 2, name: 'Case Competition' }], (e) => { built += 1; return e.name; });
  assert.deepEqual(searchIndex(index, 'sprint').map((e) => e.id), [1]);
  assert.deepEqual(searchIndex(index, 'c', '', 1).map((e) => e.id), [2]);
  assert.deepEqual(searchIndex(index, '  '), []);
  assert.equal(built, 2);
});

test('header search merges server matches with in-memory pages and records', () => {
  const remote = remoteSearchEntries({
    students: [{ id: 4, title: 'Zafar Aliyev', subtitle: 'School A' }],
    accounts: [{ id: 9, title: 'Hidden' }],
    tasks: [{ id: 1, title: '' }],
  }, { students: 'students', accounts: null, tasks: 'tasks' });
  assert.deepEqual(remote, [{ id: 'students-4', kind: 'record', destination: 'students', title: 'Zafar Aliyev', subtitle: 'School A', filterQuery: 'Zafar Aliyev' }]);
  const local = [
    { id: 'students-4', kind: 'record', title: 'Zafar Aliyev (local)' },
    { id: 'page-students', kind: 'page', title: 'Students' },
    { id: 'tasks-2', kind: 'record', title: 'Essay' },
  ];
  assert.deepEqual(mergeSearchResults(local, remote).map((entry) => entry.id), ['page-students', 'students-4', 'tasks-2']);
  assert.equal(mergeSearchResults(local, remote, 2).length, 2);
});
