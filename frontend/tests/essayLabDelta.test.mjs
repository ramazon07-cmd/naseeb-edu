import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import {
  MAX_EDIT_DISTANCE, applyOps, canonicalJson, diffDocs, docHash, normalizeDoc, prepareDoc, sha256Ascii,
} from '../src/essayLab/docDelta.js';
import { createSaveQueue } from '../src/essayLab/saveQueue.js';

// Copied from backend/apps/admissions/essay_lab/fixtures/doc_delta_cases.json (shared with the backend tests).
const fixtures = JSON.parse(readFileSync(new URL('./fixtures/doc_delta_cases.json', import.meta.url), 'utf8'));

const text = (value, marks) => (marks ? {type: 'text', text: value, marks: marks.map((type) => ({type}))} : {type: 'text', text: value});
const para = (value) => (value ? {type: 'paragraph', content: [text(value)]} : {type: 'paragraph'});
const docOf = (...blocks) => ({type: 'doc', content: blocks});

// Small deterministic PRNG so failures can be replayed.
function rng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

for (const fixture of fixtures.hash_cases) {
  test(`hash parity with the backend: ${fixture.name}`, () => {
    const normalized = normalizeDoc(fixture.input);
    assert.deepEqual(normalized, fixture.normalized);
    assert.equal(canonicalJson(normalized), fixture.canonical);
    assert.equal(docHash(normalized), fixture.hash);
    assert.equal(prepareDoc(fixture.input).hash, fixture.hash);
  });
}

for (const fixture of fixtures.invalid_cases) {
  test(`rejected like the backend: ${fixture.name}`, () => {
    assert.equal(normalizeDoc(fixture.doc), null);
    assert.equal(prepareDoc(fixture.doc), null);
  });
}

for (const fixture of fixtures.delta_cases) {
  test(`delta parity with the backend: ${fixture.name}`, () => {
    const base = prepareDoc(fixture.base);
    const next = prepareDoc(fixture.result);
    assert.deepEqual(diffDocs(base, next), fixture.ops, 'the fixture was produced by this diff');
    assert.deepEqual(applyOps(fixture.base.content, fixture.ops), fixture.result.content);
    assert.equal(next.hash, fixture.doc_hash);
  });
}

test('sha256 matches node:crypto across block boundaries', () => {
  for (const length of [0, 1, 55, 56, 57, 63, 64, 65, 119, 120, 1000, 70_000]) {
    const input = 'a{"b":[1]}\\u00e9'.repeat(Math.ceil(length / 16) + 1).slice(0, length);
    assert.equal(sha256Ascii(input), createHash('sha256').update(input).digest('hex'), `length ${length}`);
  }
});

test('canonical JSON is ASCII, sorted and compact like Python json.dumps(ensure_ascii=True)', () => {
  assert.equal(canonicalJson({b: 1, a: ['é', '😀', '\u007f', '\n"\\'], c: null}), '{"a":["\\u00e9","\\ud83d\\ude00","\\u007f","\\n\\"\\\\"],"b":1,"c":null}');
});

test('normalizeDoc mirrors the server: unknown attrs dropped, invalid docs -> null', () => {
  assert.deepEqual(normalizeDoc({type: 'doc', content: [{type: 'paragraph', attrs: {textAlign: null}, content: [text('')]}]}), docOf(para('')));
  assert.deepEqual(normalizeDoc({type: 'doc', content: []}), docOf(para('')));
  assert.equal(normalizeDoc({type: 'doc', content: [{type: 'iframe'}]}), null);
  assert.equal(normalizeDoc({type: 'doc', content: [{type: 'heading', attrs: {level: 4}}]}), null);
  assert.equal(normalizeDoc({type: 'doc', content: [{type: 'paragraph', marks: [{type: 'bold'}]}]}), null);
  assert.deepEqual(normalizeDoc({type: 'doc', content: [{type: 'paragraph', marks: []}]}), docOf(para('')));
  assert.equal(normalizeDoc({type: 'doc', content: [para('x')], extra: 1}).extra, undefined);
});

function randomBlock(random) {
  const words = ['bread', 'Ўзбек', 'radio', '😀', 'a"b', 'c\\d', 'naseeb', 'patience'];
  const value = Array.from({length: 1 + Math.floor(random() * 8)}, () => words[Math.floor(random() * words.length)]).join(' ');
  const kind = random();
  if (kind < 0.7) return para(value);
  if (kind < 0.85) return {type: 'heading', attrs: {level: random() < 0.5 ? 1 : 2}, content: [text(value, random() < 0.3 ? ['bold'] : null)]};
  return {type: 'bulletList', content: [{type: 'listItem', content: [para(value)]}]};
}

// One random editing session step: type into, insert, delete, move or replace blocks.
function randomEdit(random, blocks) {
  const next = blocks.map((block) => structuredClone(block));
  const edits = 1 + Math.floor(random() * 4);
  for (let i = 0; i < edits; i += 1) {
    const at = Math.floor(random() * (next.length + 1));
    const kind = random();
    if (kind < 0.35 && at < next.length && next[at].type === 'paragraph') {
      const current = next[at].content?.[0]?.text || '';
      const cut = Math.floor(random() * (current.length + 1));
      next[at] = para(current.slice(0, cut) + ' typed 😀' + current.slice(cut));
    } else if (kind < 0.55) next.splice(at, 0, randomBlock(random));
    else if (kind < 0.75 && next.length > 1) next.splice(Math.min(at, next.length - 1), 1 + Math.floor(random() * 2));
    else if (kind < 0.85 && next.length > 2) { const [moved] = next.splice(Math.min(at, next.length - 1), 1); next.splice(Math.floor(random() * next.length), 0, moved); }
    else if (at < next.length) next[at] = randomBlock(random);
  }
  return next.length ? next : [para('')];
}

test('property: applyOps(diffDocs(a, b), a) == b for random edit sequences', () => {
  for (let seed = 1; seed <= 60; seed += 1) {
    const random = rng(seed);
    let blocks = Array.from({length: 1 + Math.floor(random() * 30)}, () => randomBlock(random));
    let base = prepareDoc(docOf(...blocks));
    for (let step = 0; step < 25; step += 1) {
      blocks = randomEdit(random, blocks);
      const next = prepareDoc(docOf(...blocks));
      const ops = diffDocs(base, next);
      const sent = JSON.parse(JSON.stringify(ops)); // as on the wire
      const applied = applyOps(base.doc.content, sent);
      assert.deepEqual(applied, next.doc.content, `seed ${seed} step ${step}`);
      assert.equal(prepareDoc(docOf(...applied)).hash, next.hash);
      let last = -1;
      for (const op of ops) { assert.ok(op.at >= last, 'ops are ascending'); last = op.at + (op.patch ? 1 : op.delete); }
      base = next;
    }
  }
});

test('property: a large rewrite past the edit-distance bound is still exact (one splice)', () => {
  const random = rng(99);
  const a = prepareDoc(docOf(...Array.from({length: 300}, () => randomBlock(random))));
  const b = prepareDoc(docOf(...Array.from({length: 280}, (_, i) => (i % 2 ? a.doc.content[i] : randomBlock(random)))));
  const ops = diffDocs(a, b);
  assert.deepEqual(applyOps(a.doc.content, ops), b.doc.content);
  const tight = diffDocs(a, b, 4);
  assert.equal(tight.length, 1, 'past the bound the changed middle is one splice');
  assert.deepEqual(applyOps(a.doc.content, tight), b.doc.content);
  assert.ok(MAX_EDIT_DISTANCE >= 16);
});

test('unchanged docs diff to no ops; inserts and deletes are minimal', () => {
  const base = prepareDoc(docOf(para('a'), para('b'), para('c')));
  assert.deepEqual(diffDocs(base, prepareDoc(docOf(para('a'), para('b'), para('c')))), []);
  assert.deepEqual(diffDocs(base, prepareDoc(docOf(para('a'), para('x'), para('b'), para('c')))), [{at: 1, delete: 0, insert: [para('x')]}]);
  assert.deepEqual(diffDocs(base, prepareDoc(docOf(para('a'), para('c')))), [{at: 1, delete: 1, insert: []}]);
});

function longEssay() {
  const sentences = Array.from({length: 180}, (_, i) => `Sentence ${i} of this long essay tells one more small true thing.`);
  return Array.from({length: 20}, (_, i) => sentences.slice(i * 9, i * 9 + 9).join(' '));
}

test('typing in one paragraph of a 2,000-word essay sends under 5% of the full doc', async () => {
  const texts = longEssay();
  const serverDoc = docOf(...texts.map(para));
  let doc = serverDoc;
  const sent = [];
  const queue = createSaveQueue({
    send: (payload) => { sent.push(payload); return Promise.resolve({save_seq: 2, doc_hash: payload.doc_hash}); },
    getSnapshot: () => ({doc, cursor: 4000}),
    storage: null, key: null, baseSeq: 1, baseDoc: serverDoc,
    setTimer: () => 0, clearTimer: () => {},
  });
  const words = texts.join(' ').split(/\s+/).length;
  assert.ok(words >= 2000, `${words} words`);
  const edited = [...texts];
  edited[11] = `${texts[11].slice(0, 200)} a few new words${texts[11].slice(200)}`;
  doc = docOf(...edited.map(para));
  queue.change();
  queue.flush();
  const full = JSON.stringify({doc, base_seq: 1, client_save_id: 'x'.repeat(20), cursor: 4000});
  const delta = JSON.stringify(sent[0]);
  assert.ok(sent[0].ops, 'sent as a delta');
  assert.ok(delta.length < full.length * 0.05, `${delta.length} vs ${full.length}`);
  assert.deepEqual(applyOps(serverDoc.content, sent[0].ops), doc.content);
});

// --- save queue with deltas ----------------------------------------------------

const flushPromises = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };

function deltaSetup({baseDoc = docOf(para('one'), para('two')), seq = 5} = {}) {
  let doc = baseDoc;
  const sent = [];
  const deferred = [];
  const timers = [];
  let ids = 0;
  const queue = createSaveQueue({
    send: (payload, opts) => { sent.push({payload, opts}); return new Promise((resolve, reject) => deferred.push({resolve, reject})); },
    getSnapshot: () => ({doc, cursor: 1}),
    storage: null, key: null, baseSeq: seq, baseDoc,
    setTimer: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearTimer: () => {},
    makeId: () => `id-${++ids}`,
    random: () => 0,
  });
  const set = (next) => { doc = next; queue.change(); };
  const answer = async (value) => { deferred.shift().resolve(value); await flushPromises(); };
  const fail = async (error) => { deferred.shift().reject(error); await flushPromises(); };
  return {queue, sent, set, answer, fail, timers};
}

test('queue: the first change after opening is a delta against the server doc', async () => {
  const s = deltaSetup();
  s.set(docOf(para('one'), para('two!')));
  s.queue.flush();
  const {payload} = s.sent[0];
  assert.equal(payload.doc, undefined);
  assert.equal(payload.base_seq, 5);
  assert.equal(payload.doc_hash, prepareDoc(docOf(para('one'), para('two!'))).hash);
  assert.equal(payload.ops.length, 1);
  assert.ok(payload.ops[0].patch, 'typing inside a block is a patch');
  await s.answer({save_seq: 6, doc_hash: payload.doc_hash});
  assert.equal(s.queue.getState().baseHash, payload.doc_hash);
  s.set(docOf(para('one'), para('two!'), para('three')));
  s.queue.flush();
  assert.deepEqual(s.sent[1].payload.ops, [{at: 2, delete: 0, insert: [para('three')]}], 'the next delta builds on the acknowledged doc');
  assert.equal(s.sent[1].payload.base_seq, 6);
});

test('queue: a doc equal to the acknowledged one is not sent at all', async () => {
  const s = deltaSetup();
  s.set(docOf(para('one'), para('two!')));
  s.set(docOf(para('one'), para('two')));
  s.queue.flush();
  assert.equal(s.sent.length, 0);
  assert.equal(s.queue.getState().status, 'saved');
  assert.equal(s.queue.getState().dirty, false);
  // Formatting-only differences the server drops count as unchanged too.
  s.set({type: 'doc', content: [{type: 'paragraph', attrs: {textAlign: null}, content: [text('one')]}, para('two')]});
  assert.equal(await s.queue.flushAndWait(), 5);
  assert.equal(s.sent.length, 0);
});

test('queue: without a known server doc the first save is full, then deltas follow', async () => {
  const s = deltaSetup({baseDoc: null});
  s.set(docOf(para('fresh')));
  s.queue.flush();
  assert.deepEqual(s.sent[0].payload.doc, docOf(para('fresh')));
  assert.equal(s.sent[0].payload.ops, undefined);
  await s.answer({save_seq: 6, doc_hash: prepareDoc(docOf(para('fresh'))).hash});
  s.set(docOf(para('fresh'), para('more')));
  s.queue.flush();
  assert.ok(s.sent[1].payload.ops);
});

test('queue: 409 resync resends the same text in full at once, with the same id', async () => {
  const s = deltaSetup();
  s.set(docOf(para('one'), para('two!')));
  s.queue.flush();
  await s.fail(Object.assign(new Error('resync'), {status: 409, details: {code: 'resync', save_seq: 5, doc: docOf(para('other'))}}));
  assert.equal(s.sent.length, 2);
  const retry = s.sent[1].payload;
  assert.deepEqual(retry.doc, docOf(para('one'), para('two!')));
  assert.equal(retry.base_seq, 5);
  assert.equal(retry.client_save_id, s.sent[0].payload.client_save_id);
  assert.equal(retry.ops, undefined);
  assert.equal(s.queue.getState().status, 'saving');
  await s.answer({save_seq: 6, doc_hash: prepareDoc(retry.doc).hash});
  assert.equal(s.queue.getState().status, 'saved');
  assert.equal(s.queue.getState().baseHash, prepareDoc(retry.doc).hash);
});

test('queue: a stored hash that differs from ours drops the base (next save is full)', async () => {
  const s = deltaSetup();
  s.set(docOf(para('one'), para('two!')));
  s.queue.flush();
  await s.answer({save_seq: 6, doc_hash: 'f'.repeat(64)});
  assert.equal(s.queue.getState().baseHash, null);
  s.set(docOf(para('one'), para('two!!')));
  s.queue.flush();
  assert.ok(s.sent[1].payload.doc);
});

test('queue: a failed delta is retried with the identical body; an idempotent replay keeps the base', async () => {
  const s = deltaSetup();
  s.set(docOf(para('one'), para('two!')));
  s.queue.flush();
  await s.fail(Object.assign(new Error('offline'), {status: 0}));
  s.timers.at(-1).fn();
  assert.equal(s.sent[1].payload, s.sent[0].payload);
  await s.answer({save_seq: 6}); // replay of a save that had landed: no hash in the answer
  assert.equal(s.queue.getState().baseHash, s.sent[0].payload.doc_hash);
});

test('queue: conflicts rebase on the server doc when the student keeps theirs', async () => {
  const s = deltaSetup();
  s.set(docOf(para('mine'), para('two')));
  s.queue.flush();
  const serverDoc = docOf(para('one'), para('two'), para('theirs'));
  await s.fail(Object.assign(new Error('conflict'), {status: 409, details: {code: 'conflict', save_seq: 9, doc: serverDoc}}));
  assert.equal(s.queue.getState().status, 'conflict');
  s.queue.keepMine(9, serverDoc);
  const {payload} = s.sent[1];
  assert.equal(payload.base_seq, 9);
  assert.deepEqual(applyOps(serverDoc.content, payload.ops), [para('mine'), para('two')]);
  // Loading the latest makes it the base; with no doc known the next save is full.
  s.queue.acceptServer(12, docOf(para('latest')));
  assert.equal(s.queue.getState().baseHash, prepareDoc(docOf(para('latest'))).hash);
  s.queue.acceptServer(13);
  assert.equal(s.queue.getState().baseHash, null);
});

test('queue: page hide sends the small delta with keepalive even for a long essay', () => {
  const texts = longEssay();
  const big = docOf(...Array.from({length: 8}, () => texts).flat().map(para)); // well over 60 KB
  const s = deltaSetup({baseDoc: big});
  s.set(docOf(...big.content, para('last words')));
  s.queue.hide();
  assert.ok(s.sent[0].payload.ops);
  assert.equal(s.sent[0].opts.keepalive, true);
});
