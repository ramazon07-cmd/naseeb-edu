import test from 'node:test';
import assert from 'node:assert/strict';
import {
  SESSION_HINT_KEY, STALE_TOKEN_KEYS, createCookieAuth, createRefresher, createSessionStore, isSignOutSignal,
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
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const noSleep = () => Promise.resolve();

function signedIn(access = 'a0', storage = memoryStorage()) {
  const store = createSessionStore(storage);
  store.save({ access });
  return { storage, store };
}

// The server side of the refresh cookie: one valid token, rotated and
// blacklisted on every use. The browser's cookie jar is shared by all tabs;
// the cookie is read when the request leaves and replaced when the response
// arrives (`latency` ms later).
function cookieServer({ latency = 5 } = {}) {
  const jar = { cookie: 'r0' };
  let valid = 'r0';
  let n = 0;
  const sent = [];
  const send = async () => {
    const cookie = jar.cookie;
    sent.push(cookie);
    if (cookie !== valid) {
      await tick(latency);
      return { ok: false, status: 401, payload: { detail: 'blacklisted' } };
    }
    n += 1;
    valid = `r${n}`;
    const access = `a${n}`;
    await tick(latency);
    jar.cookie = valid;
    return { ok: true, status: 200, payload: { access } };
  };
  return { send, sent, jar };
}

// BroadcastChannel stand-in: delivers to every other tab, asynchronously.
function channelHub() {
  const tabs = [];
  return (store) => {
    const self = { store };
    tabs.push(self);
    return (access) => {
      for (const tab of tabs) if (tab !== self) setTimeout(() => tab.store.adopt(access), 0);
    };
  };
}

function mutex() {
  let tail = Promise.resolve();
  return (fn) => {
    const run = tail.then(fn);
    tail = run.catch(() => {});
    return run;
  };
}

// --- session store ---------------------------------------------------------

test('the access token lives in memory only; storage holds a non-secret counter', () => {
  const { storage, store } = signedIn('secret-access');
  assert.equal(store.get('access'), 'secret-access');
  assert.equal(store.get('refresh'), null);
  store.save({ access: 'a1', refresh: 'should-not-be-kept' });
  assert.deepEqual([...storage.map.entries()], [[SESSION_HINT_KEY, '2']]);
});

test('a reloaded page has no access token but knows a cookie session may exist', () => {
  const storage = memoryStorage({ [SESSION_HINT_KEY]: '7' });
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

test('a token shared by another tab is adopted only while signed in', () => {
  const storage = memoryStorage();
  const store = createSessionStore(storage);
  store.adopt('late');
  assert.equal(store.get('access'), null, 'signed out: a late broadcast must not sign this tab back in');
  storage.setItem(SESSION_HINT_KEY, '3');
  store.adopt('shared');
  assert.equal(store.get('access'), 'shared');
  assert.equal(storage.getItem(SESSION_HINT_KEY), '3', 'adopting is not a rotation');
});

test('removing the session counter (or clearing storage) signals sign-out to other tabs', () => {
  assert.equal(isSignOutSignal({ key: SESSION_HINT_KEY, newValue: null }), true);
  assert.equal(isSignOutSignal({ key: null, newValue: null }), true);
  assert.equal(isSignOutSignal({ key: SESSION_HINT_KEY, newValue: '4' }), false);
  assert.equal(isSignOutSignal({ key: 'naseeb-edu-theme', newValue: null }), false);
});

// --- refresher, one tab ----------------------------------------------------

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

test('a rejected refresh ends the session when no other tab refreshed', async () => {
  const { storage, store } = signedIn();
  let calls = 0;
  const refresh = createRefresher({ store, expired, failed, sleep: noSleep, send: async () => { calls += 1; return { ok: false, status: 401, payload: null }; } });
  await assert.rejects(refresh('a0'), (error) => error.message === 'expired' && error.status === 401);
  assert.equal(calls, 1, 'no retry: nobody rotated the cookie');
  assert.equal(store.get('access'), null);
  assert.equal(storage.getItem(SESSION_HINT_KEY), null);
});

test('a 403 (CSRF/Origin check) from refresh signs out and warns instead of retrying forever', async () => {
  const { store } = signedIn();
  const warnings = [];
  const refresh = createRefresher({
    store, expired, failed, sleep: noSleep, warn: (message) => warnings.push(message),
    send: async () => ({ ok: false, status: 403, payload: { code: 'csrf_failed' } }),
  });
  await assert.rejects(refresh('a0'), (error) => error.message === 'expired' && error.status === 401);
  assert.equal(store.hasSession(), false);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /403/);
});

test('server errors and network failures keep the session', async () => {
  for (const status of [500, 503, 0]) {
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

// --- refresher, several tabs (shared storage + cookie, separate memory) ----

test('without Web Locks, the tab that loses the race retries with the rotated cookie instead of signing everyone out', async () => {
  const storage = memoryStorage();
  const server = cookieServer({ latency: 10 });
  const tabA = signedIn('a0', storage);
  const tabB = { store: createSessionStore(storage) };
  tabB.store.adopt('a0');
  const refreshA = createRefresher({ store: tabA.store, expired, failed, send: server.send });
  const refreshB = createRefresher({ store: tabB.store, expired, failed, send: server.send, settleMs: 30 });
  const [a, b] = await Promise.all([refreshA('a0'), refreshB('a0')]);
  assert.equal(a, 'a1');
  assert.equal(b, 'a2', 'tab B lost with r0, saw the generation move and retried with r1');
  assert.deepEqual(server.sent, ['r0', 'r0', 'r1']);
  assert.notEqual(storage.getItem(SESSION_HINT_KEY), null, 'still signed in');
});

test('the losing tab reuses a token another tab shared instead of rotating again', async () => {
  const storage = memoryStorage();
  const server = cookieServer({ latency: 10 });
  const hub = channelHub();
  const tabA = signedIn('a0', storage);
  const tabB = { store: createSessionStore(storage) };
  tabB.store.adopt('a0');
  const refreshA = createRefresher({ store: tabA.store, expired, failed, send: server.send, share: hub(tabA.store) });
  const refreshB = createRefresher({ store: tabB.store, expired, failed, send: server.send, share: hub(tabB.store), settleMs: 30 });
  const [a, b] = await Promise.all([refreshA('a0'), refreshB('a0')]);
  assert.deepEqual([a, b], ['a1', 'a1']);
  assert.deepEqual(server.sent, ['r0', 'r0'], 'no second rotation');
});

test('with Web Locks, tabs waiting behind a refresh reuse the shared token: five tabs, one rotation', async () => {
  const storage = memoryStorage({ [SESSION_HINT_KEY]: '1' });
  const server = cookieServer();
  const hub = channelHub();
  const lock = mutex();
  const tabs = Array.from({ length: 5 }, () => {
    const store = createSessionStore(storage);
    return createRefresher({ store, expired, failed, send: server.send, lock, share: hub(store) });
  });
  // Five reloaded tabs, none with an access token yet.
  const results = await Promise.all(tabs.map((refresh) => refresh()));
  assert.deepEqual(server.sent, ['r0']);
  assert.deepEqual(results, ['a1', 'a1', 'a1', 'a1', 'a1']);
});

test('with Web Locks and no channel, waiting tabs still never send a used cookie', async () => {
  const storage = memoryStorage({ [SESSION_HINT_KEY]: '1' });
  const server = cookieServer();
  const lock = mutex();
  const tabs = Array.from({ length: 3 }, () => createRefresher({
    store: createSessionStore(storage), expired, failed, send: server.send, lock, handoffMs: 1,
  }));
  const results = await Promise.all(tabs.map((refresh) => refresh()));
  assert.deepEqual(server.sent, ['r0', 'r1', 'r2']);
  assert.deepEqual(results, ['a1', 'a2', 'a3']);
});

test('without a lock, tabs wait a random jitter before refreshing', async () => {
  const { store } = signedIn();
  const server = cookieServer();
  const delays = [];
  const sleep = (ms) => { delays.push(ms); return tick(ms); };
  const refresh = createRefresher({ store, expired, failed, send: server.send, jitterMs: 300, random: () => 0.2, sleep });
  assert.equal(await refresh('a0'), 'a1');
  assert.deepEqual(delays, [60]);
});

// --- cookie client (mock fetch) --------------------------------------------

function mockFetch(responses) {
  const calls = [];
  const request = async (url, options) => {
    calls.push({ url, options });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    const { status = 200, body = '' } = next || {};
    return { ok: status >= 200 && status < 300, status, text: async () => body };
  };
  return { request, calls };
}

test('refresh is a body-less POST carrying the cookie and the CSRF header', async () => {
  const fetch = mockFetch([{ status: 200, body: '{"access":"a1"}' }]);
  const auth = createCookieAuth({ apiUrl: 'https://api.example.com/api', request: fetch.request });
  assert.deepEqual(await auth.refresh(), { ok: true, status: 200, payload: { access: 'a1' } });
  const [{ url, options }] = fetch.calls;
  assert.equal(url, 'https://api.example.com/api/auth/token/refresh/');
  assert.equal(options.method, 'POST');
  assert.equal(options.credentials, 'include');
  assert.equal(options.headers['X-Requested-With'], 'XMLHttpRequest');
  assert.equal(options.body, undefined, 'the refresh token is never in a body');
});

test('logout posts to the logout endpoint with the cookie, header and keepalive', async () => {
  const fetch = mockFetch([{ status: 204 }]);
  const auth = createCookieAuth({ apiUrl: '/api', request: fetch.request, logoutTimeoutMs: 1234 });
  assert.equal(await auth.logout(), true);
  const [{ url, options }] = fetch.calls;
  assert.equal(url, '/api/auth/logout/');
  assert.equal(options.credentials, 'include');
  assert.equal(options.headers['X-Requested-With'], 'XMLHttpRequest');
  assert.equal(options.keepalive, true);
  assert.equal(options.timeoutMs, 1234);
});

test('a failed logout is retried once; it reports failure only when both tries fail', async () => {
  const flaky = mockFetch([new Error('offline'), { status: 204 }]);
  assert.equal(await createCookieAuth({ apiUrl: '/api', request: flaky.request }).logout(), true);
  assert.equal(flaky.calls.length, 2);

  const down = mockFetch([{ status: 502 }, new Error('timeout'), { status: 204 }]);
  assert.equal(await createCookieAuth({ apiUrl: '/api', request: down.request }).logout(), false);
  assert.equal(down.calls.length, 2, 'one retry, no more');
});

test('sign-in can wait for a pending logout, and concurrent logouts share one request', async () => {
  let release;
  const calls = [];
  const request = (url) => {
    calls.push(url);
    return new Promise((resolve) => { release = () => resolve({ ok: true, status: 204, text: async () => '' }); });
  };
  const auth = createCookieAuth({ apiUrl: '/api', request });
  assert.equal(await auth.settled(), true, 'nothing pending');
  const first = auth.logout();
  const second = auth.logout();
  let settled = false;
  const waiting = auth.settled().then(() => { settled = true; });
  await tick(5);
  assert.equal(settled, false, 'sign-in still waits');
  assert.equal(calls.length, 1);
  release();
  await waiting;
  assert.equal(await first, true);
  assert.equal(await second, true);
  assert.equal(settled, true);
});
