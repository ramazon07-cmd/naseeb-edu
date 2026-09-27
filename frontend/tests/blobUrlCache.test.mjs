import test from 'node:test';
import assert from 'node:assert/strict';
import { createBlobUrlCache } from '../src/lib/blobUrlCache.js';

function harness(max) {
  let next = 0;
  const revoked = [];
  const cache = createBlobUrlCache({ max, createUrl: () => `blob:${++next}`, revokeUrl: (url) => revoked.push(url) });
  return { cache, revoked };
}

test('each (id, version) is fetched once and shared by concurrent callers', async () => {
  const { cache } = harness(4);
  let calls = 0;
  const load = async () => { calls += 1; return 'bytes'; };
  const [a, b] = await Promise.all([cache.load('7:v1', load), cache.load('7:v1', load)]);
  assert.equal(a, b);
  assert.equal(await cache.load('7:v1', load), a);
  assert.equal(cache.peek('7:v1'), a);
  assert.equal(calls, 1);
  await cache.load('7:v2', load);
  assert.equal(calls, 2, 'a new version is a new key');
});

test('least recently used entries are evicted and their URLs revoked', async () => {
  const { cache, revoked } = harness(2);
  const load = async () => 'bytes';
  const one = await cache.load('1', load);
  const two = await cache.load('2', load);
  assert.equal(cache.peek('1'), one); // 1 becomes most recent
  await cache.load('3', load);
  assert.deepEqual(revoked, [two]);
  assert.equal(cache.peek('2'), '');
  assert.equal(cache.peek('1'), one);
  assert.equal(cache.size, 2);
});

test('failed loads are not cached, so the next render retries', async () => {
  const { cache } = harness(2);
  await assert.rejects(cache.load('1', async () => { throw new Error('offline'); }), /offline/);
  assert.equal(cache.size, 0);
  assert.match(await cache.load('1', async () => 'bytes'), /^blob:/);
});

test('an entry evicted mid-load is kept for its caller; clear revokes and rejects', async () => {
  const { cache, revoked } = harness(1);
  let release;
  const slow = cache.load('slow', () => new Promise((resolve) => { release = resolve; }));
  await cache.load('fast', async () => 'bytes');
  assert.equal(cache.peek('slow'), '');
  release('bytes');
  const url = await slow;
  assert.equal(cache.peek('slow'), url);
  assert.equal(revoked.length, 1, 'the older completed entry made room');

  const pending = cache.load('late', () => new Promise((resolve) => { release = resolve; }));
  await Promise.resolve(); // loadBlob starts on the next microtask
  cache.clear();
  release('bytes');
  await assert.rejects(pending, /cleared/);
  assert.equal(cache.size, 0);
  assert.ok(revoked.includes(url));
});
