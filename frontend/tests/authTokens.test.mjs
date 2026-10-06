import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  SESSION_HINT_KEY, STALE_TOKEN_KEYS, createRefresher, createSessionStore, isSignOutSignal,
} from '../src/authTokens.js';

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

function signedIn(access = 'a0') {
  const storage = memoryStorage();
  const store = createSessionStore(storage);
  store.save({ access });
  return { storage, store };
}

// The server side of the refresh cookie: one valid token, rotated and
// blacklisted on every use. The browser's cookie jar is shared by all tabs.
function cookieServer() {
  const jar = { cookie: 'r0' };
  let valid = 'r0';
  let n = 0;
  const sent = [];
  const send = async () => {
    const cookie = jar.cookie;
    sent.push(cookie);
    await new Promise((r) => setTimeout(r, 5));
    if (cookie !== valid) return { ok: false, status: 401, payload: { detail: 'blacklisted' } };
    n += 1;
    valid = `r${n}`;
    jar.cookie = valid;
    return { ok: true, status: 200, payload: { access: `a${n}` } };
  };
  return { send, sent, jar };
}

test('the access token lives in memory only; storage holds a non-secret flag', () => {
  const { storage, store } = signedIn('secret-access');
  assert.equal(store.get('access'), 'secret-access');
  assert.equal(store.get('refresh'), null);
  assert.deepEqual([...storage.map.entries()], [[SESSION_HINT_KEY, '1']]);
  assert.ok(![...storage.map.values()].some((value) => value.includes('secret')));
  // A refresh response never carries the refresh token, and one that did is not stored.
  store.save({ access: 'a1', refresh: 'should-not-be-kept' });
  assert.deepEqual([...storage.map.entries()], [[SESSION_HINT_KEY, '1']]);
});

test('a reloaded page has no access token but knows a cookie session may exist', () => {
  const storage = memoryStorage({ [SESSION_HINT_KEY]: '1' });
  const store = createSessionStore(storage);
  assert.equal(store.get('access'), null);
  assert.equal(store.hasSession(), true);
  store.clear();
  assert.equal(store.hasSession(), false);
  assert.equal(storage.getItem(SESSION_HINT_KEY), null);
});

test('tokens stored by the old frontend are removed on first use', () => {
  const initial = Object.fromEntries(STALE_TOKEN_KEYS.map((key) => [key, 'old']));
  const storage = memoryStorage({ ...initial, other: 'x' });
  const store = createSessionStore(storage);
  assert.equal(store.hasSession(), false, 'old tokens are not a session: the user signs in once');
  assert.deepEqual([...storage.map.keys()], ['other']);
});

test('blocked storage still gives an in-memory session', () => {
  const store = createSessionStore(() => { throw new Error('SecurityError'); });
  assert.equal(store.hasSession(), false);
  store.save({ access: 'a1' });
  assert.equal(store.get('access'), 'a1');
  assert.equal(store.hasSession(), true);
});

test('removing the session flag (or clearing storage) signals sign-out to other tabs', () => {
  assert.equal(isSignOutSignal({ key: SESSION_HINT_KEY, newValue: null }), true);
  assert.equal(isSignOutSignal({ key: null, newValue: null }), true);
  assert.equal(isSignOutSignal({ key: SESSION_HINT_KEY, newValue: '1' }), false);
  assert.equal(isSignOutSignal({ key: 'naseeb-edu-theme', newValue: null }), false);
});

test('parallel 401s share one refresh', async () => {
  const { store } = signedIn();
  const server = cookieServer();
  const refresh = createRefresher({ store, expired, failed, send: server.send });
  const results = await Promise.all(Array.from({ length: 20 }, () => refresh('a0')));
  assert.deepEqual(server.sent, ['r0']);
  assert.ok(results.every((value) => value === 'a1'));
  assert.equal(store.get('access'), 'a1');
});

test('a fresh page (no access token) restores the session from the cookie', async () => {
  const store = createSessionStore(memoryStorage({ [SESSION_HINT_KEY]: '1' }));
  const server = cookieServer();
  const refresh = createRefresher({ store, expired, failed, send: server.send });
  assert.equal(await refresh(), 'a1');
  assert.equal(store.get('access'), 'a1');
});

test('a caller holding a stale access token reuses the already-refreshed one', async () => {
  const { store } = signedIn('a5');
  let calls = 0;
  const refresh = createRefresher({ store, expired, failed, send: async () => { calls += 1; return { ok: true, status: 200, payload: { access: 'x' } }; } });
  assert.equal(await refresh('a4'), 'a5');
  assert.equal(calls, 0);
});

test('a rejected refresh ends the session', async () => {
  const { storage, store } = signedIn();
  const refresh = createRefresher({ store, expired, failed, send: async () => ({ ok: false, status: 401, payload: null }) });
  await assert.rejects(refresh('a0'), (error) => error.message === 'expired' && error.status === 401);
  assert.equal(store.get('access'), null);
  assert.equal(storage.getItem(SESSION_HINT_KEY), null);
});

test('server errors and a rejected CSRF check keep the session', async () => {
  for (const status of [503, 403, 0]) {
    const { store } = signedIn();
    const refresh = createRefresher({ store, expired, failed, send: async () => ({ ok: false, status, payload: null }) });
    await assert.rejects(refresh('a0'), (error) => error.message === 'failed');
    assert.equal(store.hasSession(), true, String(status));
  }
});

test('a new refresh can start after the previous one settled', async () => {
  const { store } = signedIn();
  const server = cookieServer();
  const refresh = createRefresher({ store, expired, failed, send: server.send });
  assert.equal(await refresh('a0'), 'a1');
  assert.equal(await refresh('a1'), 'a2');
  assert.deepEqual(server.sent, ['r0', 'r1']);
});

function mutex() {
  let tail = Promise.resolve();
  return (fn) => {
    const run = tail.then(fn);
    tail = run.catch(() => {});
    return run;
  };
}

// Two tabs share the cookie jar but not memory: each has its own store and refresher.
test('across tabs a shared lock serialises refreshes, so neither sends a used cookie', async () => {
  const server = cookieServer();
  const lock = mutex();
  const tabA = signedIn('a0');
  const tabB = signedIn('a0');
  const refreshA = createRefresher({ store: tabA.store, expired, failed, send: server.send, lock });
  const refreshB = createRefresher({ store: tabB.store, expired, failed, send: server.send, lock });
  const results = await Promise.all([refreshA('a0'), refreshB('a0'), refreshA('a0'), refreshB('a0')]);
  assert.deepEqual(server.sent, ['r0', 'r1']);
  assert.deepEqual(results, ['a1', 'a2', 'a1', 'a2']);
  assert.equal(server.jar.cookie, 'r2');
});

test('without a lock, tabs wait a random jitter before refreshing', async () => {
  const { store } = signedIn();
  const server = cookieServer();
  const delays = [];
  const sleep = (ms) => { delays.push(ms); return new Promise((r) => setTimeout(r, ms)); };
  const refresh = createRefresher({ store, expired, failed, send: server.send, jitterMs: 300, random: () => 0.2, sleep });
  assert.equal(await refresh('a0'), 'a1');
  assert.deepEqual(delays, [60]);
});

test('no request helper reads tokens from storage or sends a refresh token in a body', () => {
  const api = readFileSync(new URL('../src/api.js', import.meta.url), 'utf8');
  assert.doesNotMatch(api, /localStorage\.(getItem|setItem)\([^)]*token/i);
  assert.doesNotMatch(api, /JSON\.stringify\(\{\s*refresh/);
  assert.match(api, /\/auth\/token\/refresh\/`, \{ method: 'POST', \.\.\.COOKIE_AUTH \}/);
  assert.match(api, /\/auth\/logout\//);
  assert.match(api, /'X-Requested-With': 'XMLHttpRequest'/);
});
