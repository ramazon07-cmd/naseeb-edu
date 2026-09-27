import test from 'node:test';
import assert from 'node:assert/strict';
import { createRevalidation } from '../src/lib/revalidation.js';

test('only quiet polls of the same conversation revalidate', () => {
  const r = createRevalidation();
  assert.equal(r.etagFor(1, true), null, 'nothing loaded yet');
  r.remember(1, 'W/"a"');
  assert.equal(r.etagFor(1, true), 'W/"a"');
  assert.equal(r.etagFor(1, false), null, 'a visible load fetches the page');
  assert.equal(r.etagFor(2, true), null, 'another conversation never reuses the tag');
  r.remember(2, null);
  assert.equal(r.etagFor(2, true), null, 'a response without an ETag is not revalidated');
  assert.equal(r.etagFor(1, true), null, 'switching away forgets the previous tag');
  r.remember(1, 'W/"b"');
  r.reset();
  assert.equal(r.etagFor(1, true), null, 'leaving the conversation forgets it');
});
