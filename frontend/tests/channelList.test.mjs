import test from 'node:test';
import assert from 'node:assert/strict';
import { channelListEmpty } from '../src/lib/channelList.js';

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
