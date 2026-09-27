import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BACKOFF_MS, createSaveQueue, draftKey, readDraft, reconcileDraft, hasUserDrafts, removeUserDrafts, writeDraft,
} from '../src/essayLab/saveQueue.js';

function memoryStorage(initial = {}, {quotaAt = Infinity} = {}) {
  const map = new Map(Object.entries(initial));
  return {
    map,
    get length() { return map.size; },
    key: (i) => [...map.keys()][i] ?? null,
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem(k, v) {
      const size = [...map.entries()].filter(([key]) => key !== k).reduce((sum, [, value]) => sum + value.length, 0) + v.length;
      if (size > quotaAt) throw Object.assign(new Error('full'), {name: 'QuotaExceededError'});
      map.set(k, String(v));
    },
    removeItem: (k) => { map.delete(k); },
  };
}

function clock() {
  let time = 1_000_000;
  let nextId = 1;
  const timers = new Map();
  return {
    now: () => time,
    setTimer(fn, ms) { const id = nextId++; timers.set(id, {at: time + ms, fn}); return id; },
    clearTimer(id) { timers.delete(id); },
    async advance(ms) {
      const end = time + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        time = due[1].at;
        due[1].fn();
        await flushPromises();
      }
      time = end;
      await flushPromises();
    },
    pending: () => timers.size,
  };
}

const flushPromises = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };

// Queue mechanics are tested with whole-doc saves (delta: false); essayLabDelta.test.mjs covers deltas.
function setup({seq = 3, storage = memoryStorage(), respond, delta = false, baseDoc = null, random = () => 0.5} = {}) {
  const c = clock();
  const sent = [];
  const statuses = [];
  const conflicts = [];
  let doc = {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: 'v0'}]}]};
  let ids = 0;
  let serverSeq = seq;
  const deferred = [];
  const send = (payload, opts) => {
    sent.push({payload, opts, at: c.now()});
    if (respond) return respond(payload, sent.length);
    return new Promise((resolve, reject) => deferred.push({resolve, reject, payload}));
  };
  const queue = createSaveQueue({
    send, storage, key: draftKey(7, 42), baseSeq: seq,
    getSnapshot: () => ({doc, cursor: 5}),
    now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer,
    makeId: () => `id-${++ids}`,
    delta, baseDoc, random,
    onStatus: (s) => statuses.push(s),
    onConflict: (d) => conflicts.push(d),
  });
  const type = (text) => { doc = {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text}]}]}; queue.change(); };
  const resolveNext = async () => { const d = deferred.shift(); serverSeq += 1; d.resolve({save_seq: serverSeq, saved_at: 'now', word_count: 1}); await flushPromises(); };
  const rejectNext = async (error) => { const d = deferred.shift(); d.reject(error); await flushPromises(); };
  return {c, queue, sent, statuses, conflicts, storage, type, resolveNext, rejectNext, deferred};
}

test('debounces: saves 3 s after typing stops', async () => {
  const s = setup();
  s.type('a'); await s.c.advance(1000);
  s.type('ab'); await s.c.advance(2999);
  assert.equal(s.sent.length, 0);
  await s.c.advance(1);
  assert.equal(s.sent.length, 1);
  assert.deepEqual(s.sent[0].payload, {doc: {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: 'ab'}]}]}, base_seq: 3, client_save_id: 'id-1', cursor: 5});
  assert.equal(s.sent[0].opts.keepalive, false);
  await s.resolveNext();
  assert.equal(s.queue.getState().seq, 4);
  assert.equal(s.statuses.at(-1), 'saved');
});

test('saves at most every 20 s while typing continues', async () => {
  const s = setup();
  for (let i = 0; i < 25; i += 1) { s.type(`t${i}`); await s.c.advance(1000); }
  assert.equal(s.sent.length, 1);
  assert.equal(s.sent[0].at, 1_000_000 + 20_000);
});

test('writes the local draft throttled to 400 ms and removes it once synced', async () => {
  const s = setup();
  const key = draftKey(7, 42);
  s.type('a');
  assert.equal(s.storage.getItem(key), null, 'written on the next tick, never inside the keystroke');
  await s.c.advance(0);
  assert.equal(readDraft(s.storage, key).base_seq, 3);
  await s.c.advance(100);
  s.type('ab'); s.type('abc');
  await s.c.advance(299);
  assert.equal(readDraft(s.storage, key).doc.content[0].content[0].text, 'a');
  await s.c.advance(1);
  assert.equal(readDraft(s.storage, key).doc.content[0].content[0].text, 'abc');
  await s.c.advance(3000);
  await s.resolveNext();
  assert.equal(s.storage.getItem(key), null);
});

test('only one save in flight; changes made meanwhile become one follow-up', async () => {
  const s = setup();
  s.type('a'); s.queue.flush();
  assert.equal(s.sent.length, 1);
  s.type('ab'); s.queue.flush();
  s.type('abc'); s.queue.flush();
  assert.equal(s.sent.length, 1, 'no second request while one is in flight');
  await s.resolveNext();
  assert.equal(s.sent.length, 2, 'exactly one follow-up');
  assert.equal(s.sent[1].payload.base_seq, 4);
  assert.equal(s.sent[1].payload.doc.content[0].content[0].text, 'abc');
  await s.resolveNext();
  assert.equal(s.sent.length, 2);
  assert.equal(s.queue.getState().status, 'saved');
});

test('a change during a save without an explicit flush is saved by the normal debounce', async () => {
  const s = setup();
  s.type('a'); s.queue.flush();
  s.type('ab');
  await s.resolveNext();
  assert.equal(s.sent.length, 1);
  assert.equal(readDraft(s.storage, draftKey(7, 42)).base_seq, 4, 'draft re-based on the new seq');
  await s.c.advance(3000);
  assert.equal(s.sent.length, 2);
});

test('retries with the same client_save_id after a jittered wait of up to 1, 2, 5, 10, 30 s', async () => {
  const s = setup();
  s.type('a'); s.queue.flush();
  const offline = Object.assign(new Error('offline'), {status: 0});
  await s.rejectNext(offline);
  assert.equal(s.queue.getState().status, 'offline');
  // random() = 0.5 -> half of each ceiling.
  const expected = [...BACKOFF_MS, 30000].map((ms) => ms / 2);
  for (let i = 0; i < expected.length; i += 1) {
    await s.c.advance(expected[i] - 1);
    assert.equal(s.sent.length, i + 1, `no retry before ${expected[i]} ms`);
    await s.c.advance(1);
    assert.equal(s.sent.length, i + 2);
    assert.equal(s.sent.at(-1).payload.client_save_id, 'id-1');
    assert.equal(s.sent.at(-1).payload, s.sent[0].payload, 'the exact same body is re-sent');
    await s.rejectNext(Object.assign(new Error('server'), {status: 502}));
  }
  assert.equal(s.queue.getState().status, 'error');
  s.queue.retryNow();
  assert.equal(s.sent.at(-1).payload.client_save_id, 'id-1');
  await s.resolveNext();
  assert.equal(s.queue.getState().status, 'saved');
});

test('newer edits wait for the retry, then go out with a new id', async () => {
  const s = setup();
  s.type('a'); s.queue.flush();
  await s.rejectNext(Object.assign(new Error('x'), {status: 503}));
  s.type('ab'); await s.c.advance(499);
  assert.equal(s.sent.length, 1);
  await s.c.advance(1);
  assert.equal(s.sent[1].payload.client_save_id, 'id-1');
  await s.resolveNext();
  await s.c.advance(3000);
  assert.equal(s.sent[2].payload.client_save_id, 'id-2');
  assert.equal(s.sent[2].payload.doc.content[0].content[0].text, 'ab');
});

test('409 stops the queue until the student keeps theirs or loads the latest', async () => {
  const s = setup();
  s.type('mine'); s.queue.flush();
  await s.rejectNext(Object.assign(new Error('conflict'), {status: 409, details: {code: 'conflict', save_seq: 9, doc: {type: 'doc'}, saved_at: 'x'}}));
  assert.equal(s.queue.getState().status, 'conflict');
  assert.equal(s.conflicts[0].save_seq, 9);
  assert.equal(readDraft(s.storage, draftKey(7, 42)).doc.content[0].content[0].text, 'mine', 'local text kept');
  s.type('mine!'); await s.c.advance(30000);
  assert.equal(s.sent.length, 1, 'nothing is sent during a conflict');
  s.queue.keepMine(9);
  assert.equal(s.sent.length, 2);
  assert.equal(s.sent[1].payload.base_seq, 9);
  assert.notEqual(s.sent[1].payload.client_save_id, s.sent[0].payload.client_save_id);
  await s.resolveNext();
  assert.equal(s.queue.getState().status, 'saved');

  const t = setup();
  t.type('x'); t.queue.flush();
  await t.rejectNext(Object.assign(new Error('conflict'), {status: 409, details: {save_seq: 12}}));
  t.queue.acceptServer(12);
  assert.equal(t.queue.getState().status, 'saved');
  assert.equal(t.storage.getItem(draftKey(7, 42)), null);
  t.type('y'); await t.c.advance(3000);
  assert.equal(t.sent[1].payload.base_seq, 12);
});

test('page hide writes the draft at once and uses keepalive only under 60 KB', async () => {
  const s = setup({respond: () => Promise.resolve({save_seq: 4})});
  s.type('short'); s.queue.hide();
  assert.equal(s.sent[0].opts.keepalive, true);
  const big = setup({respond: () => new Promise(() => {})});
  big.type('x'.repeat(70 * 1024)); big.queue.hide();
  assert.equal(big.sent[0].opts.keepalive, false);
  assert.ok(readDraft(big.storage, draftKey(7, 42)), 'draft written immediately, not throttled');
});

test('non-retryable errors (400/413) wait for a manual retry', async () => {
  const s = setup();
  s.type('a'); s.queue.flush();
  await s.rejectNext(Object.assign(new Error('too large'), {status: 413, details: {code: 'doc_too_large'}}));
  assert.equal(s.queue.getState().status, 'error');
  await s.c.advance(60000);
  assert.equal(s.sent.length, 1);
  s.queue.retryNow();
  assert.equal(s.sent.length, 2);
  assert.equal(s.sent[1].payload.client_save_id, 'id-2');
});

test('flushAndWait resolves with the synced seq', async () => {
  const s = setup({respond: () => Promise.resolve({save_seq: 8})});
  assert.equal(await s.queue.flushAndWait(), 3);
  s.type('a');
  assert.equal(await s.queue.flushAndWait(), 8);
});

test('QuotaExceededError never evicts other (unsynced) drafts', () => {
  const storage = memoryStorage({'naseeb-essay-draft:7:1': 'x'.repeat(50), 'naseeb-essay-draft:8:2': 'y'.repeat(50), other: 'keep'}, {quotaAt: 120});
  const result = writeDraft(storage, 'naseeb-essay-draft:7:3', {doc: {type: 'doc'}, base_seq: 1, updated_at: 'x'});
  assert.deepEqual(result, {ok: false, quota: true});
  assert.equal(storage.getItem('naseeb-essay-draft:7:1'), 'x'.repeat(50));
  assert.equal(storage.getItem('naseeb-essay-draft:8:2'), 'y'.repeat(50));
  assert.equal(storage.getItem('other'), 'keep');
  assert.deepEqual(writeDraft(memoryStorage(), 'naseeb-essay-draft:7:3', {doc: 1}), {ok: true, quota: false});
});

test('reconcileDraft: push, ask or discard', () => {
  const server = {save_seq: 5, last_edited_at: '2026-09-22T21:14:00Z', doc: {type: 'doc', content: []}};
  const doc = {type: 'doc', content: [{type: 'paragraph'}]};
  assert.equal(reconcileDraft(null, server), 'none');
  assert.equal(reconcileDraft({doc, base_seq: 5, updated_at: '2026-09-22T21:15:00Z'}, server), 'push');
  assert.equal(reconcileDraft({doc, base_seq: 4, updated_at: '2026-09-22T21:15:00Z'}, server), 'ask');
  // A device clock behind the server must not throw away unsynced text.
  assert.equal(reconcileDraft({doc, base_seq: 5, updated_at: '2026-09-22T21:13:00Z'}, server), 'push');
  // Same content with keys in another order (server-validated doc) is not a change.
  const reordered = {content: [{type: 'paragraph'}], type: 'doc'};
  assert.equal(reconcileDraft({doc: reordered, base_seq: 4, updated_at: '2026-09-22T21:15:00Z'}, {...server, doc}), 'discard');
  assert.equal(reconcileDraft({doc: server.doc, base_seq: 4, updated_at: '2026-09-22T21:15:00Z'}, server), 'discard');
  assert.equal(reconcileDraft({doc, base_seq: 0, updated_at: '2026-09-22T21:15:00Z'}, {save_seq: 0, last_edited_at: null}), 'push');
});

test('logout: forget() makes one keepalive attempt and never writes a draft again', async () => {
  const s = setup();
  s.type('secret'); s.queue.forget();
  assert.equal(s.sent.length, 1);
  assert.equal(s.sent[0].opts.keepalive, true);
  s.storage.map.clear();
  await s.rejectNext(Object.assign(new Error('401'), {status: 0}));
  await s.c.advance(60000);
  assert.equal(s.storage.getItem(draftKey(7, 42)), null);
  assert.equal(s.sent.length, 1, 'no retries after logout');
});

test('client_save_id matches the backend pattern', () => {
  const sent = [];
  const q = createSaveQueue({send: (p) => { sent.push(p); return Promise.resolve({save_seq: sent.length}); }, getSnapshot: () => ({doc: {}}), storage: null, key: null});
  q.change(); q.flush();
  assert.match(sent[0].client_save_id, /^[A-Za-z0-9._:-]{1,64}$/);
});

test('401 (session expired) keeps the draft and stops syncing until an explicit retry', async () => {
  const s = setup();
  s.type('late'); s.queue.flush();
  await s.rejectNext(Object.assign(new Error('expired'), {status: 401}));
  assert.equal(s.queue.getState().status, 'expired');
  assert.ok(readDraft(s.storage, draftKey(7, 42)), 'text kept on this device');
  s.type('more'); await s.c.advance(120000);
  assert.equal(s.sent.length, 1, 'no automatic retries');
  assert.equal(readDraft(s.storage, draftKey(7, 42)).doc.content[0].content[0].text, 'more');
  s.queue.retryNow();
  assert.equal(s.sent.length, 2);
});

test('syncBeforeLogout makes a real save and reports whether everything synced', async () => {
  const ok = setup({respond: () => Promise.resolve({save_seq: 4})});
  assert.equal(await ok.queue.syncBeforeLogout(), true, 'nothing to save');
  ok.type('a');
  assert.equal(await ok.queue.syncBeforeLogout(), true);
  assert.equal(ok.sent.length, 1);
  assert.equal(ok.sent[0].opts.keepalive, false, 'a normal request, not fire-and-forget');
  assert.equal(ok.storage.getItem(draftKey(7, 42)), null);

  const expired = setup({respond: () => Promise.reject(Object.assign(new Error('expired'), {status: 401}))});
  expired.type('b');
  assert.equal(await expired.queue.syncBeforeLogout(), false);
  assert.ok(readDraft(expired.storage, draftKey(7, 42)), 'draft kept for the next sign-in');
  assert.equal(await expired.queue.syncBeforeLogout(), false, 'still unsynced, no new request');
  assert.equal(expired.sent.length, 1);
});

test('sign-out removes only the signing-out user\'s drafts', () => {
  const storage = memoryStorage({'naseeb-essay-draft:7:1': 'a', 'naseeb-essay-draft:7:2': 'b', 'naseeb-essay-draft:70:1': 'c', 'naseeb-essay-draft:8:1': 'd', other: 'e'});
  assert.equal(hasUserDrafts(storage, 7), true);
  assert.equal(removeUserDrafts(storage, 7), 2);
  assert.equal(hasUserDrafts(storage, 7), false);
  assert.equal(hasUserDrafts(storage, 70), true);
  assert.deepEqual([...storage.map.keys()].sort(), ['naseeb-essay-draft:70:1', 'naseeb-essay-draft:8:1', 'other']);
});

test('retry waits are spread uniformly below each ceiling (full jitter)', async () => {
  for (const [value, first] of [[0, 0], [0.25, 250], [0.999, 999]]) {
    const s = setup({random: () => value});
    s.type('a'); s.queue.flush();
    await s.rejectNext(Object.assign(new Error('offline'), {status: 0}));
    await s.c.advance(Math.max(0, first - 1));
    if (first > 0) assert.equal(s.sent.length, 1, `no retry before ${first} ms`);
    await s.c.advance(1);
    assert.equal(s.sent.length, 2, `retried at ${first} ms`);
  }
});

test('a discarded queue (deleted tab) sends nothing more and a late 404 does not mark it dirty', async () => {
  const s = setup();
  s.type('v1');
  s.queue.flush('manual');
  assert.equal(s.sent.length, 1);
  s.type('v2');
  s.queue.discard();
  await s.rejectNext(Object.assign(new Error('Not found.'), {status: 404}));
  assert.equal(s.queue.getState().dirty, false);
  assert.notEqual(s.queue.getState().status, 'error');
  s.queue.flush('leave');
  s.queue.retryNow();
  s.queue.hide();
  await s.c.advance(60_000);
  assert.equal(s.sent.length, 1, 'no save goes to the deleted tab');
  assert.equal(await s.queue.syncBeforeLogout(), true);
  assert.equal(await s.queue.flushAndWait(), 3);
  assert.equal(s.storage.getItem(draftKey(7, 42)), null);
});

test('discarding settles anyone waiting for the save', async () => {
  const s = setup();
  s.type('v1');
  const waiting = s.queue.flushAndWait();
  s.queue.discard();
  assert.equal(await waiting, 3);
});
