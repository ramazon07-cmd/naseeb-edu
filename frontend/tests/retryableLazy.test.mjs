// A chunk that failed to load can be retried without reloading the page,
// and the error boundary resets when the page changes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { boundaryStateFor, lazyWithRetry, retryFailedImports } from '../src/lib/retryableLazy.js';

const fakeLazy = (load) => ({ load });

test('a failed import is re-armed by retryFailedImports and imports again', async () => {
  let calls = 0;
  const factory = () => { calls += 1; return calls === 1 ? Promise.reject(new Error('chunk failed')) : Promise.resolve({ default: 'Page' }); };
  const Page = lazyWithRetry(factory, fakeLazy);
  const first = Page.current();
  await assert.rejects(first.load(), /chunk failed/);
  assert.equal(retryFailedImports(), 1);
  const second = Page.current();
  assert.notEqual(second, first, 'a fresh lazy component replaces the failed one');
  assert.deepEqual(await second.load(), { default: 'Page' });
  assert.equal(calls, 2);
  assert.equal(retryFailedImports(), 0, 'nothing left to retry');
});

test('successful imports are not re-armed', async () => {
  const Page = lazyWithRetry(() => Promise.resolve({ default: 'Ok' }), fakeLazy);
  const current = Page.current();
  await current.load();
  retryFailedImports();
  assert.equal(Page.current(), current);
});

test('the boundary clears a failure when the page (resetKey) changes', () => {
  assert.equal(boundaryStateFor('tasks', { failed: true, resetKey: 'tasks' }), null);
  assert.deepEqual(boundaryStateFor('essay_lab', { failed: true, resetKey: 'tasks' }), { failed: false, resetKey: 'essay_lab' });
});
