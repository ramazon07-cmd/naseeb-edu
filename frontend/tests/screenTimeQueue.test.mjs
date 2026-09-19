import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanScreenTimeQueue } from '../src/screenTimeQueue.js';

test('drops expired or malformed telemetry and merges valid duplicates', () => {
  const valid = {date: '2026-09-14', page: 'dashboard', seconds: 20};
  assert.deepEqual(cleanScreenTimeQueue([
    valid, valid, {...valid, date: '2026-09-06'}, {...valid, date: '2026-09-15'},
    {...valid, seconds: 0}, {...valid, page: ''}, null,
  ], '2026-09-14'), [{...valid, seconds: 40}]);
  assert.deepEqual(cleanScreenTimeQueue({}, '2026-09-14'), []);
  assert.equal(cleanScreenTimeQueue([{...valid, date: '2026-09-07'}], '2026-09-14').length, 1);
});
