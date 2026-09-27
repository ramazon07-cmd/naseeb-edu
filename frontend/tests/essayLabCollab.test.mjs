import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ensureBids, normalizeDoc, prepareDoc } from '../src/essayLab/docDelta.js';
import { BlockConflict, applyOpsV2, blockHash, changedRange, diffBlocksV2, mergeBlocks, transplantMarks } from '../src/essayLab/docMerge.js';
import { deriveText } from '../src/essayLab/docText.js';
import { createSaveQueue } from '../src/essayLab/saveQueue.js';
import {
  POLL_ACTIVE_MS, POLL_IDLE_MS, acceptAllIds, collabPollDelay, feedbackItems, historyLine, openCount, replaceById,
} from '../src/essayLab/collabModel.js';
import { accessOf, setSharing, sharingFields } from '../src/essayLab/sharing.js';

// Copied from backend/apps/admissions/essay_lab/fixtures/doc_delta_cases.json (shared with the backend tests).
const fixtures = JSON.parse(readFileSync(new URL('./fixtures/doc_delta_cases.json', import.meta.url), 'utf8'));

const text = (value, marks) => (marks ? {type: 'text', text: value, marks} : {type: 'text', text: value});
const para = (bid, value) => ({type: 'paragraph', attrs: {bid}, content: [text(value)]});
const docOf = (...blocks) => ({type: 'doc', content: blocks});

for (const fixture of fixtures.bid_cases) {
  test(`block ids like the backend: ${fixture.name}`, () => {
    assert.deepEqual(ensureBids(fixture.input), fixture.output);
  });
}

for (const fixture of fixtures.v2_cases) {
  test(`ops v2 parity with the backend: ${fixture.name}`, () => {
    const base = prepareDoc(fixture.base);
    const next = prepareDoc(fixture.result);
    assert.deepEqual(diffBlocksV2(base, next), fixture.ops_v2);
    assert.deepEqual(applyOpsV2(base.doc.content, fixture.ops_v2), next.doc.content);
    assert.equal(next.hash, fixture.doc_hash);
  });
}

for (const fixture of fixtures.merge_cases) {
  test(`per-paragraph merge like the backend: ${fixture.name}`, () => {
    const stored = prepareDoc(fixture.stored).doc.content;
    if (fixture.conflicts) {
      assert.throws(() => applyOpsV2(stored, fixture.ops_v2), (error) => error instanceof BlockConflict && JSON.stringify(error.bids) === JSON.stringify(fixture.conflicts));
    } else {
      assert.deepEqual(applyOpsV2(stored, fixture.ops_v2), fixture.merged.content);
    }
  });
}

test('the sanitizer keeps top-level ids and collaboration marks, and drops what the server drops', () => {
  const doc = normalizeDoc(docOf(
    {type: 'paragraph', attrs: {bid: 'a'}, content: [text('x', [{type: 'comment', attrs: {id: 1}}, {type: 'comment', attrs: {id: 2}}, {type: 'comment', attrs: {id: 1}}])]},
    {type: 'paragraph', attrs: {bid: 'a'}, content: [text('y')]},
    {type: 'blockquote', content: [{type: 'paragraph', attrs: {bid: 'inner'}, content: [text('z')]}]},
  ));
  assert.deepEqual(doc.content[0].content[0].marks, [{type: 'comment', attrs: {id: 1}}, {type: 'comment', attrs: {id: 2}}]);
  assert.equal(doc.content[1].attrs, undefined, 'a repeated id is dropped from the later block');
  assert.equal(doc.content[2].content[0].attrs, undefined, 'nested blocks carry no id');
  assert.equal(normalizeDoc(docOf({type: 'paragraph', content: [text('x', [{type: 'suggestInsert', attrs: {id: 'x'}}])]})), null);
});

test('suggested insertions are not the student’s text; suggested deletions still are', () => {
  const derived = deriveText(docOf({type: 'paragraph', content: [
    text('Keep '), text('gone ', [{type: 'suggestDelete', attrs: {id: 1}}]), text('added ', [{type: 'suggestInsert', attrs: {id: 2}}]), text('end.'),
  ]}));
  assert.equal(derived.content, 'Keep gone end.');
  assert.equal(derived.wordCount, 3);
});

test('diff by id sends only the changed paragraph and the hash of what it replaced', () => {
  const base = prepareDoc(docOf(para('a', 'One'), para('b', 'Two'), para('c', 'Three')));
  const next = prepareDoc(docOf(para('a', 'One'), para('b', 'Two!'), para('c', 'Three')));
  const ops = diffBlocksV2(base, next);
  assert.deepEqual(ops, [{set: 'b', base: blockHash(base.doc.content[1]), block: next.doc.content[1]}]);
  assert.equal(diffBlocksV2(prepareDoc(docOf({type: 'paragraph'})), next), null, 'a block without an id: no v2');
});

test('three-way merge keeps both sides’ changes to different paragraphs', () => {
  const base = docOf(para('a', 'One'), para('b', 'Two'), para('c', 'Three'));
  const local = docOf(para('a', 'One (student)'), para('b', 'Two'), para('c', 'Three'), para('n', 'New here'));
  const server = docOf(para('a', 'One'), para('b', 'Two'), {type: 'paragraph', attrs: {bid: 'c'}, content: [text('Three', [{type: 'comment', attrs: {id: 9}}])]});
  const {doc, conflicts} = mergeBlocks(base, local, server);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc.content.map((block) => block.attrs.bid), ['a', 'b', 'c', 'n']);
  assert.equal(doc.content[0].content[0].text, 'One (student)');
  assert.deepEqual(doc.content[2].content[0].marks, [{type: 'comment', attrs: {id: 9}}]);
});

test('three-way merge: the same paragraph changed on both sides keeps the local text and reports it', () => {
  const base = docOf(para('a', 'One'), para('b', 'Two'));
  const {doc, conflicts} = mergeBlocks(base, docOf(para('a', 'Mine'), para('b', 'Two')), docOf(para('a', 'Theirs'), para('b', 'Two'), para('s', 'Server new')));
  assert.deepEqual(conflicts, ['a']);
  assert.deepEqual(doc.content.map((block) => block.content[0].text), ['Mine', 'Two', 'Server new']);
  // Deleted on the server and untouched here: gone. Deleted here: stays deleted.
  const merged = mergeBlocks(base, docOf(para('b', 'Two')), docOf(para('a', 'One'))).doc;
  assert.deepEqual(merged.content, []);
  assert.equal(mergeBlocks(base, docOf({type: 'paragraph'}), base), null);
});

test('changedRange finds the smallest block range to swap', () => {
  const a = [para('a', '1'), para('b', '2'), para('c', '3')];
  assert.equal(changedRange(a, a), null);
  assert.deepEqual(changedRange(a, [a[0], para('b', 'x'), a[2]]), {from: 1, currentTo: 2, nextTo: 2});
  assert.deepEqual(changedRange(a, [a[0], a[2]]), {from: 1, currentTo: 2, nextTo: 1});
});

function queueHarness(respond) {
  const sent = [];
  const merged = [];
  let doc = docOf(para('a', 'One'), para('b', 'Two'));
  const queue = createSaveQueue({
    send: (payload) => { sent.push(payload); return Promise.resolve(respond(payload)); },
    getSnapshot: () => ({doc}), storage: null, key: null, baseSeq: 1, baseDoc: doc,
    setTimer: () => 0, clearTimer: () => {},
    onMerged: (serverDoc, sentDoc) => merged.push({serverDoc, sentDoc}),
  });
  return {queue, sent, merged, edit: (next) => { doc = next; queue.change(); }};
}

test('the save queue sends ops by block id once every block has one', async () => {
  const h = queueHarness(() => ({save_seq: 2, doc_hash: 'x'}));
  h.edit(docOf(para('a', 'One'), para('b', 'Two!')));
  h.queue.flush();
  await Promise.resolve();
  assert.equal(h.sent[0].ops, undefined);
  assert.equal(h.sent[0].ops_v2.length, 1);
  assert.equal(h.sent[0].ops_v2[0].set, 'b');
  assert.equal(h.sent[0].base_seq, 1);
});

test('a merged save becomes the new base and hands the server doc to the editor', async () => {
  const server = docOf(para('a', 'One', ), para('b', 'Two!'), para('c', 'Counselor-made'));
  const h = queueHarness(() => ({save_seq: 5, merged: true, doc: server, doc_hash: 'h'}));
  h.edit(docOf(para('a', 'One'), para('b', 'Two!')));
  h.queue.flush();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(h.queue.getState().seq, 5);
  assert.deepEqual(h.queue.getBaseDoc(), prepareDoc(server).doc);
  assert.equal(h.merged.length, 1);
  assert.deepEqual(h.merged[0].serverDoc, server);
  // adopt(): a newer version merged by polling becomes the base without a save.
  assert.equal(h.queue.adopt(6, docOf(para('a', 'One'))), true);
  assert.equal(h.queue.getState().seq, 6);
});

test('feedback cards follow the text; resolved threads go last', () => {
  const threads = [
    {id: 1, status: 'open', created_at: '2026-09-01'},
    {id: 2, status: 'resolved', created_at: '2026-09-02'},
    {id: 3, status: 'open', created_at: '2026-09-03'},
  ];
  const suggestions = [{id: 5, status: 'pending', created_at: '2026-09-04'}, {id: 6, status: 'accepted'}];
  const positions = new Map([['thread:3', 10], ['suggestion:5', 4]]);
  const {open, resolved} = feedbackItems(threads, suggestions, positions);
  assert.deepEqual(open.map((item) => `${item.kind}:${item.id}:${item.anchored}`), ['suggestion:5:true', 'thread:3:true', 'thread:1:false']);
  assert.deepEqual(resolved.map((item) => item.id), [2]);
  assert.equal(openCount(threads, suggestions), 3);
  assert.deepEqual(acceptAllIds(suggestions, new Set([5, 6])), [5]);
  assert.deepEqual(replaceById(threads, {id: 2, status: 'open'})[1], {id: 2, status: 'open'});
});

test('polling is fast only while someone else is in the essay', () => {
  assert.equal(collabPollDelay(true), POLL_ACTIVE_MS);
  assert.equal(collabPollDelay(false), POLL_IDLE_MS);
  assert.equal(POLL_ACTIVE_MS, 5000);
  assert.equal(POLL_IDLE_MS, 30000);
});

test('history names who suggested and who decided', () => {
  assert.deepEqual(historyLine({kind: 'suggest', author_name: 'Madina', detail: {suggestions: 2}}), {key: '{name} suggested {n} edits', n: 2, name: 'Madina'});
  assert.equal(historyLine({kind: 'suggest', detail: {suggestions: 1}}).key, '{name} suggested 1 edit');
  assert.equal(historyLine({kind: 'decision', author_name: 'Ramazon', detail: {accepted: 1, rejected: 0}}).key, '{name} accepted 1 suggestion');
  assert.equal(historyLine({kind: 'decision', detail: {accepted: 0, rejected: 3}}).key, '{name} rejected {n} suggestions');
  assert.equal(historyLine({kind: 'decision', detail: {accepted: 2, rejected: 1}}).key, '{name} accepted {a} and rejected {r} suggestions');
  assert.equal(historyLine({kind: 'edit'}), null);
});

test('sharing sends the chosen counselor access and keeps it from the answer', async () => {
  const calls = [];
  const api = {shareEssay: async (...args) => { calls.push(args); return {id: 1, shared_with_counselor: true, shared_at: 'now', counselor_access: 'comment'}; }};
  const saved = await setSharing(api, {id: 1}, true, 'comment');
  assert.deepEqual(calls, [[1, 'comment']]);
  assert.equal(sharingFields(saved).counselor_access, 'comment');
  assert.equal(accessOf({counselor_access: 'edit'}), 'suggest', 'the dialog offers comment or suggest; anything else shows the default');
});

test('a comment added to the paragraph the student is typing in moves onto the new text', () => {
  const base = para('a', 'I learned patience slowly.');
  const local = para('a', 'Honestly, I learned patience slowly.');
  const server = {type: 'paragraph', attrs: {bid: 'a'}, content: [
    text('I learned '), text('patience', [{type: 'comment', attrs: {id: 4}}]), text(' slowly.'),
  ]};
  const moved = transplantMarks(base, local, server);
  assert.deepEqual(moved.content, [
    text('Honestly, I learned '), text('patience', [{type: 'comment', attrs: {id: 4}}]), text(' slowly.'),
  ]);
  const {doc, conflicts} = mergeBlocks(docOf(base), docOf(local), docOf(server));
  assert.deepEqual(conflicts, []);
  assert.deepEqual(doc.content[0], moved);
  // Commented words the student replaced: the highlight covers the replacement; other server edits stay conflicts.
  assert.deepEqual(transplantMarks(base, para('a', 'I learned calm slowly.'), server).content,
    [text('I learned '), text('calm', [{type: 'comment', attrs: {id: 4}}]), text(' slowly.')]);
  assert.deepEqual(transplantMarks(base, para('a', 'I learned patienc'), server).content, [text('I learned patienc')],
    'an end inside the rewritten part drops the mark');
  assert.equal(transplantMarks(base, local, para('a', 'Server rewrote it.')), null);
  const bold = {type: 'paragraph', attrs: {bid: 'a'}, content: [text('I learned patience slowly.', [{type: 'bold'}])]};
  assert.equal(transplantMarks(base, local, bold), null, 'formatting changes are not feedback marks');
});
