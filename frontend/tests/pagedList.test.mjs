import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_PAGE_SIZE, createPageCache, createPagedController, cursorFromNext, listKey, listQuery, mergePage,
} from '../src/lib/pagedList.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {resolve = res;reject = rej;});
  return { promise, resolve, reject };
}

// A fake server: every call is recorded and answered by the test.
function harness({ cache = null, debounceMs = 300 } = {}) {
  const calls = [];
  const timers = [];
  const states = [];
  const controller = createPagedController({
    resource: 'tasks',
    cache,
    debounceMs,
    fetchPage: (resource, query, signal) => {
      const call = { resource, query, signal, ...deferred() };
      calls.push(call);
      return call.promise;
    },
    onChange: (state) => states.push(state),
    schedule: (callback, ms) => {timers.push({ callback, ms, cancelled: false });return timers.length - 1;},
    cancelSchedule: (id) => {timers[id].cancelled = true;},
  });
  const flushTimers = () => timers.filter((timer) => !timer.cancelled && !timer.fired).forEach((timer) => {timer.fired = true;timer.callback();});
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  return { controller, calls, timers, states, flushTimers, settle, state: () => controller.getState() };
}

const page = (ids, next = null) => ({ results: ids.map((id) => ({ id })), next, has_more: Boolean(next) });
const nextLink = (cursor) => `http://api.test/api/tasks/?cursor=${cursor}&page_size=25`;

test('listQuery always asks for a cursor page and keeps a stable parameter order', () => {
  assert.equal(listQuery(), '?cursor=&page_size=25');
  assert.equal(
    listQuery({ search: '  zafar ', filters: { status: 'todo', student: 4, school: '', grade: 'all', counselor: null }, ordering: 'due', pageSize: 10 }),
    '?cursor=&page_size=10&search=zafar&ordering=due&status=todo&student=4',
  );
  assert.equal(listQuery({ pageSize: 10_000 }), `?cursor=&page_size=${MAX_PAGE_SIZE}`);
  assert.equal(listQuery({ cursor: 'abc' }), '?cursor=abc&page_size=25');
  assert.equal(listKey('tasks', { filters: { b: 1, a: 2 } }), listKey('tasks', { filters: { a: 2, b: 1 } }));
});

test('cursorFromNext reads the cursor from absolute and relative links', () => {
  assert.equal(cursorFromNext(nextLink('eyJv')), 'eyJv');
  assert.equal(cursorFromNext('/api/tasks/?page_size=5&cursor=x1'), 'x1');
  assert.equal(cursorFromNext(null), null);
});

test('mergePage never duplicates a row', () => {
  assert.deepEqual(mergePage([{ id: 1 }, { id: 2 }], [{ id: 2 }, { id: 3 }]).map((item) => item.id), [1, 2, 3]);
});

test('the page cache expires entries, evicts the least recently used and invalidates per resource', () => {
  let now = 0;
  const cache = createPageCache({ limit: 2, ttlMs: 100, now: () => now });
  cache.set('tasks?a', { items: [1] });
  cache.set('students?a', { items: [2] });
  assert.deepEqual(cache.get('tasks?a').items, [1]);
  cache.set('essays?a', { items: [3] });
  assert.equal(cache.get('students?a'), null, 'least recently used entry evicted');
  assert.ok(cache.get('tasks?a'));
  now = 500;
  assert.equal(cache.get('tasks?a'), null, 'expired');
  cache.set('tasks?b', { items: [] });
  cache.set('users/accounts?c', { items: [] });
  cache.invalidate(['tasks']);
  assert.equal(cache.get('tasks?b'), null);
  assert.ok(cache.get('users/accounts?c'));
});

test('first page, then load more with the returned cursor', async () => {
  const h = harness();
  h.controller.setParams({ search: '', filters: { student: 7 } });
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].query, '?cursor=&page_size=25&student=7');
  assert.equal(h.state().loading, true);
  h.calls[0].resolve(page([1, 2], nextLink('c1')));
  await h.settle();
  assert.deepEqual(h.state().items.map((item) => item.id), [1, 2]);
  assert.equal(h.state().hasMore, true);
  h.controller.loadMore();
  h.controller.loadMore(); // ignored while the page is loading
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].query, '?cursor=c1&page_size=25&student=7');
  h.calls[1].resolve(page([2, 3]));
  await h.settle();
  assert.deepEqual(h.state().items.map((item) => item.id), [1, 2, 3]);
  assert.equal(h.state().hasMore, false);
  h.controller.loadMore();
  assert.equal(h.calls.length, 2, 'nothing more to load');
});

test('search is debounced: one request after typing pauses', async () => {
  const h = harness();
  h.controller.setParams({ search: '' });
  h.calls[0].resolve(page([1]));
  await h.settle();
  for (const term of ['z', 'za', 'zaf', 'zafar']) h.controller.setParams({ search: term });
  assert.equal(h.calls.length, 1, 'no request while typing');
  assert.equal(h.timers.filter((timer) => !timer.cancelled).length, 1);
  assert.equal(h.timers.at(-1).ms, 300);
  assert.deepEqual(h.state().items.map((item) => item.id), [1], 'current rows stay visible');
  h.flushTimers();
  assert.equal(h.calls.length, 2);
  assert.match(h.calls[1].query, /search=zafar/);
});

test('filter changes apply at once and cancel a pending search', () => {
  const h = harness();
  h.controller.setParams({ search: '' });
  h.controller.setParams({ search: 'ali' });
  h.controller.setParams({ search: 'ali', filters: { status: 'late' } });
  assert.equal(h.timers[0].cancelled, true);
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].query, '?cursor=&page_size=25&search=ali&status=late');
});

test('a newer request aborts the older one and a stale response is ignored', async () => {
  const h = harness({ debounceMs: 0 });
  h.controller.setParams({ search: 'a' });
  h.controller.setParams({ search: 'ab' });
  assert.equal(h.calls[0].signal.aborted, true);
  assert.equal(h.calls[1].signal.aborted, false);
  h.calls[1].resolve(page([2]));
  await h.settle();
  h.calls[0].resolve(page([1])); // arrives late
  await h.settle();
  assert.deepEqual(h.state().items.map((item) => item.id), [2]);
});

test('an aborted request never reports an error', async () => {
  const h = harness({ debounceMs: 0 });
  h.controller.setParams({ search: 'a' });
  h.controller.setParams({ search: 'b' });
  const abort = new Error('aborted');
  abort.name = 'AbortError';
  h.calls[0].reject(abort);
  h.calls[1].resolve(page([5]));
  await h.settle();
  assert.equal(h.state().error, '');
  assert.deepEqual(h.state().items.map((item) => item.id), [5]);
});

test('errors are reported and the list can be reloaded', async () => {
  const h = harness();
  h.controller.setParams({});
  h.calls[0].reject(new Error('Server unavailable'));
  await h.settle();
  assert.equal(h.state().error, 'Server unavailable');
  assert.equal(h.state().loading, false);
  h.controller.reload();
  h.calls[1].resolve(page([1]));
  await h.settle();
  assert.equal(h.state().error, '');
  assert.equal(h.state().items.length, 1);
});

test('returning to cached parameters renders without a request', async () => {
  const cache = createPageCache();
  const h = harness({ cache, debounceMs: 0 });
  h.controller.setParams({ filters: { status: 'todo' } });
  h.calls[0].resolve(page([1, 2], nextLink('c1')));
  await h.settle();
  h.controller.loadMore();
  h.calls[1].resolve(page([3]));
  await h.settle();
  h.controller.setParams({ filters: { status: 'late' } });
  h.calls[2].resolve(page([9]));
  await h.settle();
  h.controller.setParams({ filters: { status: 'todo' } });
  assert.equal(h.calls.length, 3, 'served from the cache');
  assert.deepEqual(h.state().items.map((item) => item.id), [1, 2, 3], 'every loaded page is kept');
  h.controller.reload();
  assert.equal(h.calls.length, 4, 'reload bypasses the cache');
});

test('a cached switch drops the in-flight request for the old parameters', async () => {
  const cache = createPageCache();
  const h = harness({ cache, debounceMs: 0 });
  h.controller.setParams({ filters: { status: 'todo' } });
  h.calls[0].resolve(page([1]));
  await h.settle();
  h.controller.setParams({ filters: { status: 'late' } });
  h.controller.setParams({ filters: { status: 'todo' } });
  assert.equal(h.calls[1].signal.aborted, true);
  h.calls[1].resolve(page([99]));
  await h.settle();
  assert.deepEqual(h.state().items.map((item) => item.id), [1]);
});

test('load more waits while a new search is pending', async () => {
  const h = harness();
  h.controller.setParams({ search: '' });
  h.calls[0].resolve(page([1], nextLink('c1')));
  await h.settle();
  h.controller.setParams({ search: 'new' });
  h.controller.loadMore();
  assert.equal(h.calls.length, 1, 'the old cursor must not be combined with the new search');
});

test('unchanged parameters do not refetch, and dispose silences late responses', async () => {
  const h = harness();
  h.controller.setParams({ search: 'x', filters: { a: 1 } });
  h.controller.setParams({ search: 'x ', filters: { a: 1 } });
  assert.equal(h.calls.length, 1);
  const before = h.states.length;
  h.controller.dispose();
  assert.equal(h.calls[0].signal.aborted, true);
  h.calls[0].resolve(page([1]));
  await h.settle();
  assert.equal(h.states.length, before);
});

test('updateItem replaces or removes one row locally', async () => {
  const h = harness();
  h.controller.setParams({});
  h.calls[0].resolve(page([1, 2, 3]));
  await h.settle();
  h.controller.updateItem(2, (item) => ({ ...item, done: true }));
  h.controller.updateItem(3, () => null);
  assert.deepEqual(h.state().items, [{ id: 1 }, { id: 2, done: true }]);
});
