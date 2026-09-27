import test from 'node:test';
import assert from 'node:assert/strict';
import { assistantSource } from '../src/lib/assistantSource.js';

test('only gateway answers are presented as AI', () => {
  assert.equal(assistantSource('gateway').ai, true);
  assert.equal(assistantSource('gateway').note, '');
  for (const mode of ['local-fallback', 'budget-exhausted', 'policy']) {
    const source = assistantSource(mode);
    assert.equal(source.ai, false, mode);
    assert.ok(source.note, `${mode} explains where the answer came from`);
  }
});

test('an unknown mode is treated as built-in text, a missing header as unknown', () => {
  assert.equal(assistantSource('something-new').ai, false);
  assert.equal(assistantSource(null), null);
  assert.equal(assistantSource(''), null);
  assert.equal(assistantSource(' Gateway ').ai, true);
});
