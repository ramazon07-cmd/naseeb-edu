import test from 'node:test';
import assert from 'node:assert/strict';
import { isShared, setSharing, sharingFields } from '../src/essayLab/sharing.js';

function fakeApi() {
  const calls = [];
  return {
    calls,
    shareEssay: async (id) => { calls.push(['share', id]); return { id, shared_with_counselor: true, shared_at: '2026-09-25T10:00:00Z', title: 'Server title' }; },
    unshareEssay: async (id) => { calls.push(['unshare', id]); return { id, shared_with_counselor: false, shared_at: null, title: 'Server title' }; },
  };
}

test('essays are private unless the server says they are shared', () => {
  assert.equal(isShared({ id: 1 }), false);
  assert.equal(isShared(null), false);
  assert.equal(isShared({ id: 1, shared_with_counselor: false }), false);
  assert.equal(isShared({ id: 1, shared_with_counselor: true }), true);
});

test('setSharing calls the matching endpoint for the requested state', async () => {
  const api = fakeApi();
  assert.equal((await setSharing(api, { id: 7 }, true)).shared_with_counselor, true);
  assert.equal((await setSharing(api, { id: 7, shared_with_counselor: true }, false)).shared_with_counselor, false);
  assert.deepEqual(api.calls, [['share', 7], ['unshare', 7]]);
});

test('only sharing fields are merged back, so local text and title stay put', async () => {
  const saved = await setSharing(fakeApi(), { id: 3 }, true);
  assert.deepEqual(sharingFields(saved), { id: 3, shared_with_counselor: true, shared_at: '2026-09-25T10:00:00Z' });
  assert.deepEqual(sharingFields({ id: 3 }), { id: 3, shared_with_counselor: false, shared_at: null });
});
