import test from 'node:test';
import assert from 'node:assert/strict';
import { canDeleteTab, createTabOpener, movedOrder, siblingsOf, tabTree } from '../src/essayLab/tabsModel.js';
import { documentStats } from '../src/essayLab/counts.js';
import { fitGroups } from '../src/essayLab/toolbarLayout.js';
import { createSessionRegistry, createTabSession, discardLocalDraft, keepLocalDraft, saveProblem, syncTabs, unsavedTabs } from '../src/essayLab/sessions.js';
import { draftKey, readDraft } from '../src/essayLab/saveQueue.js';
import { normalizeHref, normalizeDoc, repairDoc } from '../src/essayLab/docDelta.js';
import { clampFontSize, toFontFamily, toFontSize, toHex } from '../src/essayLab/formatting.js';

const tabs = [
  { id: 1, parent: null, position: 0, title: 'General', word_count: 10, char_count: 50, char_count_no_spaces: 40 },
  { id: 2, parent: null, position: 1, title: 'Who am I', word_count: 3, char_count: 12, char_count_no_spaces: 10 },
  { id: 3, parent: 2, position: 0, title: 'Autobiography', word_count: 5, char_count: 30, char_count_no_spaces: 25 },
  { id: 4, parent: null, position: 2, title: 'PS', word_count: 0, char_count: 0, char_count_no_spaces: 0 },
  { id: 5, parent: 2, position: 1, title: 'Values', word_count: 1, char_count: 5, char_count_no_spaces: 5 },
];

test('tabs are listed parents first, each followed by its sub-tabs', () => {
  assert.deepEqual(tabTree(tabs).map(({ tab, children }) => [tab.id, children.map((child) => child.id)]), [[1, []], [2, [3, 5]], [4, []]]);
  assert.deepEqual(siblingsOf(tabs, tabs[2]).map((tab) => tab.id), [3, 5]);
});

test('move up / down reorders siblings only and stops at the ends', () => {
  assert.deepEqual(movedOrder(tabs, tabs[1], -1), [2, 1, 4]);
  assert.deepEqual(movedOrder(tabs, tabs[4], -1), [5, 3]);
  assert.equal(movedOrder(tabs, tabs[0], -1), null);
  assert.equal(movedOrder(tabs, tabs[3], 1), null);
});

test('the counter adds the open tab live to the other tabs saved counts', () => {
  const live = { tab: 3, wordCount: 8, charCount: 40, charCountNoSpaces: 33 };
  assert.deepEqual(documentStats(tabs, 3, live), {
    tab: { words: 8, chars: 40, charsNoSpaces: 33 },
    document: { words: 8 + 10 + 3 + 0 + 1, chars: 40 + 50 + 12 + 0 + 5, charsNoSpaces: 33 + 40 + 10 + 0 + 5 },
  });
  // Stale live stats from another tab are ignored.
  assert.equal(documentStats(tabs, 1, live).tab.words, 10);
});

test('toolbar groups that do not fit go to the More menu', () => {
  const groups = [{ width: 100 }, { width: 100 }, { width: 100 }];
  assert.equal(fitGroups(1000, groups), 3);
  assert.equal(fitGroups(250, groups), 1); // 48 for More + two padded groups > 250
  assert.equal(fitGroups(40, groups), 0);
});

test('pasted HTML values become allowed attributes or nothing', () => {
  assert.equal(toHex('rgb(185, 28, 28)'), '#b91c1c');
  assert.equal(toHex('#ABC'), '#aabbcc');
  assert.equal(toHex('rgba(0, 0, 0, 0)'), null);
  assert.equal(toHex('red'), null);
  assert.equal(toFontFamily("'Times New Roman', serif"), 'Times New Roman');
  assert.equal(toFontFamily('"Lora Variable", serif'), 'Lora');
  assert.equal(toFontFamily('Comic Sans MS'), null);
  assert.equal(toFontSize('12pt'), 12);
  assert.equal(toFontSize('16px'), 12);
  assert.equal(toFontSize('200pt'), 96);
  assert.equal(toFontSize('1em'), null);
  assert.equal(clampFontSize(3), 8);
});

test('link box input becomes an allowed href', () => {
  assert.equal(normalizeHref('https://mit.edu/admissions'), 'https://mit.edu/admissions');
  assert.equal(normalizeHref('mit.edu'), 'https://mit.edu');
  assert.equal(normalizeHref('me@example.com'), 'mailto:me@example.com');
  assert.equal(normalizeHref('javascript:alert(1)'), null);
  assert.equal(normalizeHref('/admin'), null);
});

test('formatting the server would reject is repaired before saving', () => {
  const doc = { type: 'doc', content: [
    { type: 'paragraph', attrs: { textAlign: 'start', lineHeight: '1.5', indent: 99 }, content: [
      { type: 'text', text: 'a', marks: [{ type: 'link', attrs: { href: '/relative', target: '_blank' } }, { type: 'bold' }] },
      { type: 'text', text: 'b', marks: [{ type: 'textStyle', attrs: { fontFamily: 'Comic Sans MS', fontSize: 12, color: '#ABCDEF' } }] },
    ] },
  ] };
  const repaired = repairDoc(doc);
  assert.deepEqual(normalizeDoc(repaired), { type: 'doc', content: [
    { type: 'paragraph', attrs: { lineHeight: '1.5' }, content: [
      { type: 'text', text: 'a', marks: [{ type: 'bold' }] },
      { type: 'text', text: 'b', marks: [{ type: 'textStyle', attrs: { fontSize: 12, color: '#abcdef' } }] },
    ] },
  ] });
  assert.equal(normalizeDoc(doc), null, 'the unrepaired doc would be rejected');
});

function memoryStorage() {
  const items = new Map();
  return {
    getItem: (key) => (items.has(key) ? items.get(key) : null),
    setItem: (key, value) => items.set(key, String(value)),
    removeItem: (key) => items.delete(key),
    key: (index) => [...items.keys()][index] ?? null,
    get length() { return items.size; },
  };
}

const para = (text) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] });

test('each tab saves with its own seq, and says which tab it is', async () => {
  const sent = [];
  const saved = [];
  const session = createTabSession({
    essayId: 9, tab: { id: 21, doc: para('one'), save_seq: 4 }, userId: 7, storage: memoryStorage(),
    send: async (payload) => { sent.push(payload); return { save_seq: payload.base_seq + 1, tab: payload.tab, word_count: 2 }; },
    onSaved: (tabId, response) => saved.push([tabId, response.save_seq]),
  });
  session.doc = para('one two');
  session.queue.change();
  await session.queue.flushAndWait();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].tab, 21);
  assert.equal(sent[0].base_seq, 4);
  assert.deepEqual(saved, [[21, 5]]);
  session.queue.close();
});

test('a draft from before tabs moves to the only tab; deleting a tab drops its draft', () => {
  const storage = memoryStorage();
  const legacy = draftKey(7, 9);
  storage.setItem(legacy, JSON.stringify({ doc: para('unsynced'), base_seq: 4, updated_at: '2026-09-25T10:00:00Z' }));
  const session = createTabSession({
    essayId: 9, tab: { id: 21, doc: para('saved'), save_seq: 4 }, userId: 7, storage, adoptLegacyDraft: true,
    send: () => new Promise(() => {}),
  });
  assert.equal(session.decision, 'push');
  assert.equal(storage.getItem(legacy), null);
  assert.ok(readDraft(storage, draftKey(7, 9, 21)));
  session.dispose();
  assert.equal(storage.getItem(draftKey(7, 9, 21)), null);
});

test('an unsynced draft on an older version waits for the student', () => {
  const storage = memoryStorage();
  storage.setItem(draftKey(7, 9, 21), JSON.stringify({ doc: para('mine'), base_seq: 2, updated_at: '2026-09-25T10:00:00Z' }));
  const session = createTabSession({ essayId: 9, tab: { id: 21, doc: para('theirs'), save_seq: 4 }, userId: 7, storage, send: () => new Promise(() => {}) });
  assert.equal(session.decision, 'ask');
  assert.equal(session.state.unsynced.doc.content[0].content[0].text, 'mine');
  discardLocalDraft(session);
  assert.equal(session.state.unsynced, null);
  assert.equal(storage.getItem(draftKey(7, 9, 21)), null);
  assert.equal(keepLocalDraft(session), null);
});

test('disposing a deleted tab with unsaved text sends nothing to it', () => {
  const storage = memoryStorage();
  const sent = [];
  const session = createTabSession({
    essayId: 9, tab: { id: 21, doc: para('saved'), save_seq: 4 }, userId: 7, storage,
    send: (payload) => { sent.push(payload); return new Promise(() => {}); },
  });
  session.doc = para('typed');
  session.queue.change();
  session.dispose();
  session.queue.flush('leave');
  assert.equal(sent.length, 0);
  assert.equal(readDraft(storage, draftKey(7, 9, 21)), null);
});

function opener({ active = 1, loaded = [1] } = {}) {
  const log = { shown: [], loading: [], failed: [], sessions: new Set(loaded), active };
  const pending = new Map();
  const open = createTabOpener({
    isOpen: (id) => id === log.active,
    hasSession: (id) => log.sessions.has(id),
    fetchTab: (id) => new Promise((resolve, reject) => pending.set(id, { resolve, reject })),
    openSession: (tab) => log.sessions.add(tab.id),
    setLoading: (id) => log.loading.push(id),
    show: (id) => { log.shown.push(id); log.active = id; },
    fail: (error) => log.failed.push(error.message),
  });
  return { log, open, pending };
}

test('a slow fetch for an earlier tab click never overrides a later click', async () => {
  const { log, open, pending } = opener();
  const first = open(2);
  const second = open(3);
  pending.get(3).resolve({ id: 3 });
  assert.equal(await second, true);
  pending.get(2).resolve({ id: 2 });
  assert.equal(await first, false);
  assert.deepEqual(log.shown, [3]);
  assert.equal(log.active, 3);
  assert.equal(log.loading.at(-1), null);
});

test('clicking an already loaded tab cancels a pending fetch, and a stale failure is silent', async () => {
  const { log, open, pending } = opener({ loaded: [1, 4] });
  const slow = open(2);
  assert.equal(await open(4), true);
  pending.get(2).reject(new Error('offline'));
  assert.equal(await slow, false);
  assert.deepEqual(log.shown, [4]);
  assert.deepEqual(log.failed, []);
  assert.deepEqual(log.loading, [2, null]);
});

test('clicking back to the open tab cancels a pending fetch; the latest failure is reported', async () => {
  const { log, open, pending } = opener();
  const slow = open(2);
  await open(1);
  pending.get(2).resolve({ id: 2 });
  await slow;
  assert.deepEqual(log.shown, []);
  const failing = open(5);
  pending.get(5).reject(new Error('gone'));
  assert.equal(await failing, false);
  assert.deepEqual(log.failed, ['gone']);
});

test('only the first tab opened in a visit is offered a draft from before tabs', () => {
  const offered = [];
  const registry = createSessionRegistry((tab, { adoptLegacyDraft }) => {
    offered.push([tab.id, adoptLegacyDraft]);
    return { id: tab.id, dispose() { this.disposed = true; } };
  });
  const first = registry.open({ id: 21 });
  registry.open({ id: 22 });
  assert.equal(registry.open({ id: 21 }), first);
  registry.open({ id: 23 });
  assert.deepEqual(offered, [[21, true], [22, false], [23, false]]);
  registry.remove(21);
  assert.equal(first.disposed, true);
  assert.equal(registry.has(21), false);
  assert.deepEqual(registry.all().map((item) => item.id), [22, 23]);
});

test('a document with several tabs adopts the old draft into the first tab opened, and a new tab never does', () => {
  const storage = memoryStorage();
  const legacy = draftKey(7, 9);
  storage.setItem(legacy, JSON.stringify({ doc: para('unsynced'), base_seq: 4, updated_at: '2026-09-25T10:00:00Z' }));
  const registry = createSessionRegistry((tab, { adoptLegacyDraft }) => createTabSession({
    essayId: 9, tab, userId: 7, storage, adoptLegacyDraft, send: () => new Promise(() => {}),
  }));
  const first = registry.open({ id: 21, doc: para('saved'), save_seq: 4 });
  assert.equal(first.decision, 'push');
  assert.equal(storage.getItem(legacy), null);
  storage.setItem(legacy, JSON.stringify({ doc: para('stale'), base_seq: 0, updated_at: '2026-09-25T10:00:00Z' }));
  const created = registry.open({ id: 30, doc: para(''), save_seq: 0 });
  assert.equal(created.decision, 'none');
  assert.equal(readDraft(storage, draftKey(7, 9, 30)), null);
});

test('an old draft is cleared when the tab already has a newer draft of its own', () => {
  const storage = memoryStorage();
  const legacy = draftKey(7, 9);
  storage.setItem(legacy, JSON.stringify({ doc: para('old'), base_seq: 1, updated_at: '2026-09-20T10:00:00Z' }));
  storage.setItem(draftKey(7, 9, 21), JSON.stringify({ doc: para('newer'), base_seq: 4, updated_at: '2026-09-25T10:00:00Z' }));
  const session = createTabSession({
    essayId: 9, tab: { id: 21, doc: para('saved'), save_seq: 4 }, userId: 7, storage, adoptLegacyDraft: true,
    send: () => new Promise(() => {}),
  });
  assert.equal(session.doc.content[0].content[0].text, 'newer');
  assert.equal(storage.getItem(legacy), null);
  session.queue.close();
});

test('save problems: conflicts and rejected text rank above retries; saving is not a problem', () => {
  assert.equal(saveProblem({ status: 'saved' }), null);
  assert.equal(saveProblem({ status: 'saving' }), null);
  assert.equal(saveProblem({ status: 'offline' }), null);
  assert.equal(saveProblem({ status: 'conflict', conflict: {} }), 'conflict');
  assert.equal(saveProblem({ status: 'error', error: { status: 413 } }), 'rejected');
  assert.equal(saveProblem({ status: 'error', error: { status: 400 } }), 'rejected');
  assert.equal(saveProblem({ status: 'error', error: { status: 503 } }), 'error');
  assert.equal(saveProblem({ status: 'error', error: { status: 429 } }), 'error');
  assert.equal(saveProblem({ status: 'expired' }), 'expired');
  const sessions = [
    { id: 1, state: { status: 'saved' } },
    { id: 2, state: { status: 'error', error: { status: 500 } } },
    { id: 3, state: { status: 'conflict', conflict: {} } },
    { id: 4, state: { status: 'error', error: { status: 413 } } },
  ];
  assert.deepEqual(unsavedTabs(sessions), [{ id: 3, problem: 'conflict' }, { id: 4, problem: 'rejected' }, { id: 2, problem: 'error' }]);
});

test('the registry reports every tab\'s save changes', () => {
  const storage = memoryStorage();
  const registry = createSessionRegistry((tab, { adoptLegacyDraft }) => createTabSession({
    essayId: 9, tab, userId: 7, storage, adoptLegacyDraft, send: () => new Promise(() => {}),
  }));
  const a = registry.open({ id: 1, doc: para('a'), save_seq: 1 });
  const b = registry.open({ id: 2, doc: para('b'), save_seq: 1 });
  let calls = 0;
  registry.subscribe(() => { calls += 1; });
  const before = registry.version();
  b.set({ status: 'conflict', conflict: {} });
  assert.equal(calls, 1);
  assert.notEqual(registry.version(), before);
  assert.deepEqual(unsavedTabs(registry.all()), [{ id: 2, problem: 'conflict' }]);
  registry.remove(2);
  b.set({ status: 'saved' });
  assert.equal(calls, 2, 'a removed tab no longer reports');
  a.queue.close();
});

test('leaving waits for every tab and names the ones left only on this device', async () => {
  const session = (id, result) => ({ id, queue: { syncBeforeLogout: () => (result instanceof Error ? Promise.reject(result) : result) } });
  assert.deepEqual(await syncTabs([session(1, Promise.resolve(true)), session(2, Promise.resolve(false)), session(3, new Error('x'))]), [2, 3]);
  let fire;
  const hang = session(4, new Promise(() => {}));
  const pending = syncTabs([session(1, Promise.resolve(true)), hang], { timeoutMs: 10, setTimer: (fn) => { fire = fn; return 1; }, clearTimer: () => {} });
  await new Promise((resolve) => setImmediate(resolve));
  fire();
  assert.deepEqual(await pending, [4]);
});

test('a restored version reports the server counts like a save does', () => {
  const saved = [];
  const session = createTabSession({
    essayId: 9, tab: { id: 21, doc: para('one'), save_seq: 4 }, userId: 7, storage: memoryStorage(),
    send: () => new Promise(() => {}), onSaved: (tabId, response) => saved.push([tabId, response]),
  });
  const detail = { save_seq: 6, word_count: 120, char_count: 700, char_count_no_spaces: 580, document_word_count: 900, last_edited_at: '2026-09-25T10:00:00Z' };
  session.applySaved({ ...detail, saved_at: detail.last_edited_at });
  assert.equal(session.state.savedAt, '2026-09-25T10:00:00Z');
  assert.equal(saved.length, 1);
  assert.equal(saved[0][0], 21);
  assert.equal(saved[0][1].document_word_count, 900);
  assert.equal(saved[0][1].word_count, 120);
});

test('the last tab, or a tab whose sub-tabs are all that is left, cannot be deleted', () => {
  assert.equal(canDeleteTab([tabs[0]], tabs[0]), false);
  assert.equal(canDeleteTab(tabs, tabs[0]), true);
  const onlyParent = [tabs[1], tabs[2], tabs[4]];
  assert.equal(canDeleteTab(onlyParent, tabs[1]), false);
  assert.equal(canDeleteTab(onlyParent, tabs[2]), true);
});
