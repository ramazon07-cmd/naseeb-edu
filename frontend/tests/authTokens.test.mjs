import test from 'node:test';
import assert from 'node:assert/strict';
import { LEGACY_TOKEN_KEYS, createRefresher, createTokenStore, TOKEN_KEYS } from '../src/authTokens.js';

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
    map,
  };
}

const expired = (status) => Object.assign(new Error('expired'), { status });
const failed = (status) => Object.assign(new Error('failed'), { status });

function setup({ access = 'a0', refresh = 'r0' } = {}) {
  const storage = memoryStorage({ [TOKEN_KEYS.access]: access, [TOKEN_KEYS.refresh]: refresh });
  const store = createTokenStore(storage);
  return { storage, store };
}

test('parallel 401s share one refresh and keep the rotated tokens', async () => {
  const { store } = setup();
  const sent = [];
  let serverRefresh = 'r0';
  let n = 0;
  const refresh = createRefresher({
    store, expired, failed,
    send: async (token) => {
      sent.push(token);
      await new Promise((r) => setTimeout(r, 5));
      if (token !== serverRefresh) return { ok: false, status: 401, payload: { detail: 'blacklisted' } };
      n += 1;
      serverRefresh = `r${n}`;
      return { ok: true, status: 200, payload: { access: `a${n}`, refresh: serverRefresh } };
    },
  });
  const results = await Promise.all(Array.from({ length: 20 }, () => refresh('a0')));
  assert.deepEqual(sent, ['r0']);
  assert.ok(results.every((value) => value === 'a1'));
  assert.equal(store.get('access'), 'a1');
  assert.equal(store.get('refresh'), 'r1');
});

test('a caller holding a stale access token reuses the already-refreshed one', async () => {
  const { store } = setup({ access: 'a5', refresh: 'r5' });
  let calls = 0;
  const refresh = createRefresher({ store, expired, failed, send: async () => { calls += 1; return { ok: true, status: 200, payload: { access: 'x' } }; } });
  assert.equal(await refresh('a4'), 'a5');
  assert.equal(calls, 0);
});

test('a rejected refresh clears tokens only if the stored refresh token was the one sent', async () => {
  const { store } = setup();
  const rotatedElsewhere = createRefresher({
    store, expired, failed,
    send: async () => {
      store.save({ access: 'other-tab-access', refresh: 'other-tab-refresh' });
      return { ok: false, status: 401, payload: null };
    },
  });
  assert.equal(await rotatedElsewhere('a0'), 'other-tab-access');
  assert.equal(store.get('refresh'), 'other-tab-refresh');

  const genuine = createRefresher({ store, expired, failed, send: async () => ({ ok: false, status: 401, payload: null }) });
  await assert.rejects(genuine('other-tab-access'), (error) => error.message === 'expired' && error.status === 401);
  assert.equal(store.get('access'), null);
  assert.equal(store.get('refresh'), null);
});

test('server errors during refresh keep the session', async () => {
  const { store } = setup();
  const refresh = createRefresher({ store, expired, failed, send: async () => ({ ok: false, status: 503, payload: null }) });
  await assert.rejects(refresh('a0'), (error) => error.message === 'failed' && error.status === 503);
  assert.equal(store.get('refresh'), 'r0');
});

test('a new refresh can start after the previous one settled', async () => {
  const { store } = setup();
  let n = 0;
  const refresh = createRefresher({ store, expired, failed, send: async () => { n += 1; return { ok: true, status: 200, payload: { access: `a${n}`, refresh: `r${n}` } }; } });
  assert.equal(await refresh('a0'), 'a1');
  assert.equal(await refresh('a1'), 'a2');
});

test('tokens stored under the old admitflow-* keys are migrated, not lost', () => {
  const storage = memoryStorage({ [LEGACY_TOKEN_KEYS.access]: 'old-a', [LEGACY_TOKEN_KEYS.refresh]: 'old-r', other: 'x' });
  const store = createTokenStore(storage);
  assert.equal(store.get('access'), 'old-a');
  assert.equal(store.get('refresh'), 'old-r');
  assert.deepEqual([...storage.map.keys()].sort(), ['naseeb-access-token', 'naseeb-refresh-token', 'other']);
});

test('a newer naseeb-* token wins over a leftover legacy one', () => {
  const storage = memoryStorage({ [TOKEN_KEYS.refresh]: 'new-r', [LEGACY_TOKEN_KEYS.refresh]: 'old-r' });
  const store = createTokenStore(storage);
  assert.equal(store.get('refresh'), 'new-r');
  assert.equal(storage.getItem(LEGACY_TOKEN_KEYS.refresh), null);
});

// Two tabs share localStorage but not memory: each has its own refresher.
function rotatingServer(store) {
  let serverRefresh = store.get('refresh');
  let n = 0;
  const sent = [];
  const send = async (token) => {
    sent.push(token);
    await new Promise((r) => setTimeout(r, 5));
    if (token !== serverRefresh) return { ok: false, status: 401, payload: { detail: 'blacklisted' } };
    n += 1;
    serverRefresh = `r${n}`;
    return { ok: true, status: 200, payload: { access: `a${n}`, refresh: serverRefresh } };
  };
  return { send, sent };
}

function mutex() {
  let tail = Promise.resolve();
  return (fn) => {
    const run = tail.then(fn);
    tail = run.catch(() => {});
    return run;
  };
}

test('across tabs a shared lock makes one refresh; the other tab reuses the new token', async () => {
  const { store } = setup();
  const server = rotatingServer(store);
  const lock = mutex();
  const tabA = createRefresher({ store, expired, failed, send: server.send, lock });
  const tabB = createRefresher({ store, expired, failed, send: server.send, lock });
  const results = await Promise.all([tabA('a0'), tabB('a0'), tabA('a0'), tabB('a0')]);
  assert.deepEqual(server.sent, ['r0']);
  assert.deepEqual(results, ['a1', 'a1', 'a1', 'a1']);
  assert.equal(store.get('refresh'), 'r1');
});

test('without a lock, tabs wait a random jitter and reuse a refresh that landed meanwhile', async () => {
  const { store } = setup();
  const server = rotatingServer(store);
  const delays = [];
  const sleep = (ms) => { delays.push(ms); return new Promise((r) => setTimeout(r, ms)); };
  const tabA = createRefresher({ store, expired, failed, send: server.send, jitterMs: 300, random: () => 0, sleep });
  const tabB = createRefresher({ store, expired, failed, send: server.send, jitterMs: 300, random: () => 0.2, sleep });
  const results = await Promise.all([tabA('a0'), tabB('a0')]);
  assert.deepEqual(delays, [0, 60]);
  assert.deepEqual(server.sent, ['r0'], 'tab B found the token tab A stored during its wait');
  assert.deepEqual(results, ['a1', 'a1']);
});
