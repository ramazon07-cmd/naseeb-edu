import test from 'node:test';
import assert from 'node:assert/strict';
import {
  SESSION_HINT_KEY, STALE_TOKEN_KEYS, createCookieAuth, createRefresher, createSessionStore, isSignOutSignal,
  migrateLegacyTokens,
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

test('the access token lives in memory only; storage holds a non-secret "<sign-in>.<refreshes>" counter', () => {
  const { storage, store } = signedIn('secret-access');
  assert.equal(store.get('access'), 'secret-access');
  assert.equal(store.get('refresh'), null);
  const [signIn, count] = storage.getItem(SESSION_HINT_KEY).split('.');
  assert.equal(count, '1');
  store.save({ access: 'a1', refresh: 'should-not-be-kept' });
  assert.deepEqual([...storage.map.entries()], [[SESSION_HINT_KEY, `${signIn}.2`]]);
  assert.ok(![...storage.map.values()].some((value) => value.includes('secret') || value.includes('kept')));
  store.save({ access: 'a2' }, { signIn: true });
  assert.notEqual(store.signInId(), signIn, 'a new sign-in gets a new id');
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

test('refresh tokens the old frontend stored are revoked on the server, then all old keys removed', async () => {
  const storage = memoryStorage({
    'naseeb-access-token': 'old-a', 'naseeb-refresh-token': 'old-r', 'admitflow-refresh-token': 'older-r', other: 'x',
  });
  const revoked = [];
  await migrateLegacyTokens(storage, async (token) => { revoked.push(token); });
  assert.deepEqual(revoked, ['old-r', 'older-r'], 'access tokens are not sent (they expire on their own)');
  assert.deepEqual([...storage.map.keys()], ['other']);
  assert.equal(createSessionStore(storage).hasSession(), false, 'old tokens are not a session: the user signs in once');
  assert.deepEqual(Object.keys(STALE_TOKEN_KEYS).sort(), ['admitflow-access-token', 'admitflow-refresh-token', 'naseeb-access-token', 'naseeb-refresh-token']);
});

test('the legacy migration still removes the tokens when the server is unreachable', async () => {
  const storage = memoryStorage({ 'naseeb-refresh-token': 'old-r' });
  await migrateLegacyTokens(storage, async () => { throw new Error('offline'); });
  assert.equal(storage.getItem('naseeb-refresh-token'), null);
  await migrateLegacyTokens(() => { throw new Error('SecurityError'); }, async () => assert.fail('no storage, nothing to send'));
});

test('a storage whose removeItem throws cannot hide the session', () => {
  const storage = memoryStorage({ [SESSION_HINT_KEY]: 'k.1' });
  storage.removeItem = () => { throw new Error('quota'); };
  assert.equal(createSessionStore(storage).hasSession(), true);
});

test('signing out ends the session in this tab at once; the counter waits for clear()', () => {
  const { storage, store } = signedIn('a1');
  const signInId = store.signInId();
  assert.equal(store.endHere(), signInId);
  assert.equal(store.get('access'), null);
  assert.equal(store.hasSession(), false, 'no silent refresh in this tab');
  assert.notEqual(storage.getItem(SESSION_HINT_KEY), null, 'other tabs are told only once the server confirmed');
  store.adopt('late-token');
  assert.equal(store.get('access'), null, 'a token shared by another tab does not sign it back in');
  store.clear(signInId);
  assert.equal(storage.getItem(SESSION_HINT_KEY), null);
});

test('a sign-out does not remove the counter of a newer sign-in from another tab', () => {
  const storage = memoryStorage();
  const tabA = signedIn('a1', storage).store;
  const tabB = createSessionStore(storage);
  const ending = tabA.endHere();
  tabB.save({ access: 'b1' }, { signIn: true });
  tabA.clear(ending);
  assert.notEqual(storage.getItem(SESSION_HINT_KEY), null);
  assert.equal(tabB.hasSession(), true);
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
  storage.setItem(SESSION_HINT_KEY, 'k.3');
  store.adopt('shared');
  assert.equal(store.get('access'), 'shared');
  assert.equal(storage.getItem(SESSION_HINT_KEY), 'k.3', 'adopting is not a rotation');
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
  const store = createSessionStore(memoryStorage({ [SESSION_HINT_KEY]: 'k.1' }));
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
  const storage = memoryStorage({ [SESSION_HINT_KEY]: 'k.1' });
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
  const storage = memoryStorage({ [SESSION_HINT_KEY]: 'k.1' });
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

test('a refresh that lands after sign-out is dropped: no token, no counter', async () => {
  const { storage, store } = signedIn('a0');
  let land;
  const refresh = createRefresher({
    store, expired, failed,
    send: () => new Promise((resolve) => { land = () => resolve({ ok: true, status: 200, payload: { access: 'a1' } }); }),
  });
  const pending = refresh('a0');
  await tick();
  const signInId = store.endHere();
  land();
  await assert.rejects(pending, (error) => error.status === 401);
  assert.equal(store.get('access'), null);
  store.clear(signInId);
  assert.equal(storage.getItem(SESSION_HINT_KEY), null, 'the late response did not write the counter back');
  await refresh.settled();
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

test('logout posts with the cookie and header, without keepalive (it breaks CORS preflights)', async () => {
  const fetch = mockFetch([{ status: 204 }]);
  const auth = createCookieAuth({ apiUrl: '/api', request: fetch.request, logoutTimeoutMs: 1234 });
  assert.equal(await auth.logout(), true);
  const [{ url, options }] = fetch.calls;
  assert.equal(url, '/api/auth/logout/');
  assert.equal(options.credentials, 'include');
  assert.equal(options.headers['X-Requested-With'], 'XMLHttpRequest');
  assert.equal(options.keepalive, undefined);
  assert.equal(options.body, undefined);
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

test('logout waits for this tab\'s in-flight refresh, then sends the newest cookie', async () => {
  const order = [];
  const jar = { cookie: 'r0' };
  const { store } = signedIn('a0');
  let land;
  const refresher = createRefresher({
    store, expired, failed,
    send: () => new Promise((resolve) => {
      order.push(`refresh sent ${jar.cookie}`);
      land = () => { jar.cookie = 'r1'; order.push('refresh landed'); resolve({ ok: true, status: 200, payload: { access: 'a1' } }); };
    }),
  });
  const request = async (url) => { order.push(`logout sent ${jar.cookie}`); return { ok: true, status: 204, text: async () => '' }; };
  const auth = createCookieAuth({ apiUrl: '/api', request, store, settleRefreshes: () => refresher.settled() });
  const refreshing = refresher('a0').catch(() => 'dropped');
  await tick();
  const signInId = store.endHere();
  const loggingOut = auth.logout(signInId);
  await tick(5);
  assert.deepEqual(order, ['refresh sent r0'], 'logout is held back while the refresh is in flight');
  land();
  assert.equal(await loggingOut, true);
  assert.equal(await refreshing, 'dropped');
  assert.deepEqual(order, ['refresh sent r0', 'refresh landed', 'logout sent r1']);
  assert.equal(store.get('access'), null);
});

test('across tabs, a sign-in waits for a sign-out holding the lock, so the logout response cannot delete the new cookie', async () => {
  const lock = mutex();
  const storage = memoryStorage();
  const tabA = signedIn('a0', storage).store;
  const tabB = createSessionStore(storage);
  const order = [];
  let finishLogout;
  const requestA = () => new Promise((resolve) => {
    order.push('logout sent');
    finishLogout = () => { order.push('logout response (deletes cookie)'); resolve({ ok: true, status: 204, text: async () => '' }); };
  });
  const authA = createCookieAuth({ apiUrl: '/api', request: requestA, store: tabA, lock });
  const authB = createCookieAuth({ apiUrl: '/api', request: async () => ({}), store: tabB, lock });
  const loggingOut = authA.logout(tabA.endHere());
  await tick();
  const signingIn = authB.signIn(async () => { order.push('login (sets cookie)'); tabB.save({ access: 'b1' }, { signIn: true }); });
  await tick(5);
  assert.deepEqual(order, ['logout sent']);
  finishLogout();
  await Promise.all([loggingOut, signingIn]);
  assert.deepEqual(order, ['logout sent', 'logout response (deletes cookie)', 'login (sets cookie)']);
});

test('a sign-out superseded by a newer sign-in in another tab is not sent', async () => {
  const storage = memoryStorage();
  const tabA = signedIn('a0', storage).store;
  const tabB = createSessionStore(storage);
  const fetch = mockFetch([{ status: 204 }]);
  const auth = createCookieAuth({ apiUrl: '/api', request: fetch.request, store: tabA });
  const ending = tabA.endHere();
  tabB.save({ access: 'b1' }, { signIn: true });
  assert.equal(await auth.logout(ending), true);
  assert.equal(fetch.calls.length, 0, 'the cookie now belongs to the newer sign-in');
  tabA.clear(ending);
  assert.equal(tabB.hasSession(), true);
});

test('sign-in waits for this tab\'s pending logout, and concurrent logouts share one request', async () => {
  let release;
  const calls = [];
  const request = (url) => {
    calls.push(url);
    return new Promise((resolve) => { release = () => resolve({ ok: true, status: 204, text: async () => '' }); });
  };
  const auth = createCookieAuth({ apiUrl: '/api', request });
  const first = auth.logout();
  const second = auth.logout();
  let signedIn = false;
  const signingIn = auth.signIn(async () => { signedIn = true; return 'ok'; });
  await tick(5);
  assert.equal(signedIn, false, 'sign-in still waits');
  assert.equal(calls.length, 1);
  release();
  assert.equal(await signingIn, 'ok');
  assert.equal(await first, true);
  assert.equal(await second, true);
});

test('a legacy token is revoked through the logout endpoint, in the body, with the CSRF header', async () => {
  const fetch = mockFetch([{ status: 204 }]);
  await createCookieAuth({ apiUrl: '/api', request: fetch.request }).revokeLegacy('old-r');
  const [{ url, options }] = fetch.calls;
  assert.equal(url, '/api/auth/logout/');
  assert.equal(options.headers['X-Requested-With'], 'XMLHttpRequest');
  assert.equal(options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(options.body), { refresh: 'old-r' });
  await assert.rejects(createCookieAuth({ apiUrl: '/api', request: mockFetch([{ status: 403 }]).request }).revokeLegacy('x'));
});
