import test from 'node:test';
import assert from 'node:assert/strict';
import { failedPage, pageAfterLoad, pageCount } from '../src/lib/studentListPage.js';

const base = { pageSize: 25, count: 0, status: 0, error: '' };

test('a loaded page past the end moves to the last page; a valid one stays', () => {
  assert.equal(pageAfterLoad({ ...base, page: 3, count: 40 }), 2);
  assert.equal(pageAfterLoad({ ...base, page: 2, count: 40 }), null);
  assert.equal(pageAfterLoad({ ...base, page: 1, count: 0 }), null);
  assert.equal(pageCount(0, 25), 1);
  assert.equal(pageCount(51, 25), 3);
});

test('a 404 (invalid page) goes to the last page the filter still has', () => {
  const gone = { ...base, error: 'Invalid page.', status: 404 };
  assert.equal(pageAfterLoad({ ...gone, page: 3, total: 30 }), 2);
  assert.equal(pageAfterLoad({ ...gone, page: 5, total: 0 }), 1);
  // Without the total, page 1; never the same page again (no loop on a stale total).
  assert.equal(pageAfterLoad({ ...gone, page: 4 }), 1);
  assert.equal(pageAfterLoad({ ...gone, page: 4, total: 1000 }), 3);
  assert.equal(pageAfterLoad({ ...gone, page: 1, total: 10 }), null);
});

test('any other failure stays on the page so its error and Retry show', () => {
  assert.equal(pageAfterLoad({ ...base, page: 2, error: 'Network down', status: 0, total: 10 }), null);
  assert.equal(pageAfterLoad({ ...base, page: 2, error: 'Server error', status: 500 }), null);
});

test('a failed request settles under its own key with no earlier rows', () => {
  assert.deepEqual(failedPage('?page=2', { message: 'Invalid page.', status: 404 }), { key: '?page=2', items: [], count: 0, loading: false, error: 'Invalid page.', status: 404 });
});
