import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeSaved } from '../src/lib/mergeSaved.js';

const letter = (id, updated_at, body = '') => ({ id, updated_at, body });

test('a copy saved on the page shows until the loaded list catches up', () => {
  const loaded = [letter(1, '2026-10-10T10:00:00Z', 'old')];
  const saved = [letter(1, '2026-10-10T10:05:00Z', 'mine')];
  assert.equal(mergeSaved(loaded, saved)[0].body, 'mine');
  // A refresh with the same or a newer version replaces the saved copy.
  assert.equal(mergeSaved([letter(1, '2026-10-10T10:05:00Z', 'server')], saved)[0].body, 'server');
  assert.equal(mergeSaved([letter(1, '2026-10-10T10:09:00Z', 'newer')], saved)[0].body, 'newer');
});

test('a letter created on the page leads the list until it is loaded, then appears once', () => {
  const created = letter(2, '2026-10-10T10:00:00Z');
  assert.deepEqual(mergeSaved([letter(1, '2026-10-09T00:00:00Z')], [created]).map((item) => item.id), [2, 1]);
  assert.deepEqual(mergeSaved([created, letter(1, '2026-10-09T00:00:00Z')], [created]).map((item) => item.id), [2, 1]);
});
