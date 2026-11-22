import test from 'node:test';
import assert from 'node:assert/strict';
import { findCounselorChannel, pinnedRows, withoutPinned } from '../src/lib/pinnedChats.js';

const counselor = { id: 7, full_name: 'Firdavs Counselor', direct_channel_id: 12 };
const chat = (id, extra = {}) => ({ id, kind: 'direct', display_name: `Chat ${id}`, ...extra });

test('a student with a counselor gets Telegram first, then the counselor', () => {
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', counselor }), ['telegram', 'counselor']);
});

test('the counselor row stays pinned with no messages and no channel yet', () => {
  const noChat = { ...counselor, direct_channel_id: null };
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', counselor: noChat }), ['telegram', 'counselor']);
  assert.equal(findCounselorChannel([], noChat), null);
});

test('a student without a counselor sees only the Telegram channel', () => {
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', counselor: null }), ['telegram']);
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'direct', counselor: null }), []);
});

test('each folder keeps the pinned rows that belong in it', () => {
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'direct', counselor }), ['counselor']);
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'group', counselor }), ['telegram']);
});

test('staff and parents get no pinned rows', () => {
  for (const role of ['counselor', 'parent', 'organization']) {
    assert.deepEqual(pinnedRows({ role, tab: 'all', counselor }), []);
  }
});

test('a search keeps only the pinned rows it matches', () => {
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', search: 'firdavs', counselor }), ['counselor']);
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', search: 'Telegram', counselor }), ['telegram']);
  assert.deepEqual(pinnedRows({ role: 'student', tab: 'all', search: 'zzz', counselor }), []);
});

test('the counselor chat moves out of the list into its pinned row', () => {
  const channels = [chat(3), chat(12, { display_name: 'Firdavs Counselor' }), chat(5, { kind: 'group' })];
  const pinned = findCounselorChannel(channels, counselor);
  assert.equal(pinned.id, 12);
  assert.deepEqual(withoutPinned(channels, pinned).map((item) => item.id), [3, 5]);
});

test('a chat the counselor opened later is found by the counselor id, never Saved Messages or a group', () => {
  const later = { ...counselor, direct_channel_id: null };
  const channels = [
    chat(1, { direct_peer_id: 7, kind: 'group' }),
    chat(2, { direct_peer_id: 7, is_saved_messages: true }),
    chat(9, { direct_peer_id: 7 }),
  ];
  assert.equal(findCounselorChannel(channels, later).id, 9);
  assert.equal(findCounselorChannel(channels, later, 2).id, 2, 'a known channel id wins');
});

test('another person with the counselor name is never taken for the counselor', () => {
  const namesake = chat(4, { display_name: 'Firdavs Counselor', direct_peer_id: 99 });
  const noChat = { ...counselor, direct_channel_id: null };
  assert.equal(findCounselorChannel([namesake], noChat), null, 'no chat yet: the placeholder stays');
  assert.equal(findCounselorChannel([namesake], counselor), null, 'the known chat is not on this page: placeholder');
  const real = chat(12, { display_name: 'Firdavs Counselor', direct_peer_id: 7 });
  assert.equal(findCounselorChannel([namesake, real], noChat).id, 12);
});

test('the rest of the list is untouched without a pinned chat', () => {
  const channels = [chat(1), chat(2)];
  assert.equal(withoutPinned(channels, null), channels);
});
