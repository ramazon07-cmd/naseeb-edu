import test from 'node:test';
import assert from 'node:assert/strict';
import { BAND_TIERS } from '../src/lib/college.js';

test('an unknown admission band maps to no tier, never "target"', () => {
  assert.deepEqual(BAND_TIERS, { reach: 'dream', target: 'target', safety: 'safety' });
  assert.equal(BAND_TIERS[null], undefined);
  assert.equal(BAND_TIERS[undefined], undefined);
});
