import test from 'node:test';
import assert from 'node:assert/strict';
import { channelListEmpty, mergeChannelPage } from '../src/lib/channelList.js';

test('the unsearched Private tab never claims to be empty', () => {
  // Saved Messages (and the counselor thread) are listed there even before any chat exists.
  assert.equal(channelListEmpty('direct', '', 0), '');
});

test('other tabs and searches explain an empty list', () => {
  assert.equal(channelListEmpty('community', '', 0), 'none');
  assert.equal(channelListEmpty('discussion', '', 0), 'none');
  assert.equal(channelListEmpty('direct', 'anna', 0), 'search');
  assert.equal(channelListEmpty('community', 'anna', 0), 'search');
});

test('a list with channels shows no note', () => {
  assert.equal(channelListEmpty('direct', '', 2), '');
  assert.equal(channelListEmpty('community', 'anna', 1), '');
});

const chat = (id, kind = 'direct', extra = {}) => ({ id, kind, ...extra });

test('a refreshed page 1 keeps the chats Load more added', () => {
  const current = [chat(1), chat(2), chat(30), chat(31), chat(9, 'group')];
  const merged = mergeChannelPage(current, 'direct', [chat(2, 'direct', { unread_count: 3 }), chat(1)], { keepLoaded: true });
  assert.deepEqual(merged.map((item) => item.id), [9, 2, 1, 30, 31]);
  assert.equal(merged.find((item) => item.id === 2).unread_count, 3, 'rows on the page are replaced');
});

test('a new search replaces the folder, other folders stay', () => {
  const merged = mergeChannelPage([chat(1), chat(30), chat(9, 'group')], 'direct', [chat(5)]);
  assert.deepEqual(merged.map((item) => item.id), [9, 5]);
});

test('the open chat off page 1 is updated or added, and dropped only when gone', () => {
  const current = [chat(1), chat(30, 'group', { is_member: false })];
  const joined = mergeChannelPage(current, 'group', [chat(2, 'group')], { keepLoaded: true, fetched: [chat(30, 'group', { is_member: true })] });
  assert.deepEqual(joined.map((item) => [item.id, item.is_member]), [[1, undefined], [2, undefined], [30, true]]);
  const searched = mergeChannelPage(current, 'group', [chat(2, 'group')], { fetched: [chat(30, 'group')] });
  assert.deepEqual(searched.map((item) => item.id), [1, 2, 30], 'kept open even when the search does not list it');
  const left = mergeChannelPage(current, 'group', [chat(2, 'group')], { keepLoaded: true, gone: [30] });
  assert.deepEqual(left.map((item) => item.id), [1, 2]);
  const otherFolder = mergeChannelPage(current, 'group', [], { fetched: [chat(7, 'direct')] });
  assert.ok(!otherFolder.some((item) => item.id === 7), "a fetched chat of another folder is not added");
});
