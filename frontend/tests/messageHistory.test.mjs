import test from 'node:test';
import assert from 'node:assert/strict';
import { compareMessages, mergeNewestPage, prependOlder, restoredScrollTop, scrollAnchor } from '../src/lib/messageHistory.js';

const at = (id, minute) => ({ id, created_at: `2026-09-25T10:${String(minute).padStart(2, '0')}:00Z` });

test('messages order by time, then id', () => {
  assert.ok(compareMessages(at(2, 1), at(1, 2)) < 0);
  assert.ok(compareMessages(at(1, 1), at(2, 1)) < 0);
});

test('a poll keeps the older pages the user loaded', () => {
  const loaded = [at(1, 1), at(2, 2), at(3, 3), at(4, 4)];
  const merged = mergeNewestPage(loaded, [at(3, 3), at(4, 4), at(5, 5)]);
  assert.deepEqual(merged.map((m) => m.id), [1, 2, 3, 4, 5]);
});

test('a poll replaces the window it covers (edits and deletions show)', () => {
  const edited = { ...at(4, 4), body: 'edited' };
  const merged = mergeNewestPage([at(3, 3), at(4, 4)], [at(3, 3), edited]);
  assert.equal(merged[1].body, 'edited');
});

test('rows that slide out of the newest window do not vanish', () => {
  const merged = mergeNewestPage([at(1, 1), at(2, 2)], [at(2, 2), at(3, 3)]);
  assert.deepEqual(merged.map((m) => m.id), [1, 2, 3]);
});

test('an empty conversation stays empty', () => {
  const empty = [];
  assert.equal(mergeNewestPage(empty, []), empty);
});

test('older pages go in front without duplicates', () => {
  const merged = prependOlder([at(3, 3), at(4, 4)], [at(1, 1), at(2, 2), at(3, 3)]);
  assert.deepEqual(merged.map((m) => m.id), [1, 2, 3, 4]);
});

test('the scroll position survives a prepend', () => {
  const list = { scrollHeight: 1000, scrollTop: 10 };
  const anchor = scrollAnchor(list);
  list.scrollHeight = 1600;
  assert.equal(restoredScrollTop(list, anchor), 610);
  assert.equal(scrollAnchor(null), null);
});
