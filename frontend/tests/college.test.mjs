import test from 'node:test';
import assert from 'node:assert/strict';
import { BAND_TIERS, collegeSorter, universityCountry, universityFit } from '../src/lib/college.js';

const student = { target_countries: 'UK', sat_score: 1450, budget_usd: 30000, scholarship_needed: false };

test('an unknown admission band maps to no tier, never "target"', () => {
  assert.deepEqual(BAND_TIERS, { reach: 'dream', target: 'target', safety: 'safety' });
  assert.equal(BAND_TIERS[null], undefined);
  assert.equal(BAND_TIERS[undefined], undefined);
});

test('the fallback fit gives no points for missing SAT or price data', () => {
  const unknown = { country: 'United Kingdom' };
  const known = { country: 'United Kingdom', sat_min: 1400, net_price_usd: 20000 };
  assert.ok(universityFit(known, student).score > universityFit(unknown, student).score);
  assert.equal(universityFit(known, student).score - universityFit(unknown, student).score, 40);
  assert.equal(universityFit({ ...unknown, test_optional: true }, student).score - universityFit(unknown, student).score, 25);
});

test('rows research did not score sort after the scored ones', () => {
  const rows = [{ id: 1, country: 'Germany' }, { id: 2, country: 'United Kingdom' }, { id: 3, country: 'United Kingdom' }];
  const fits = new Map([[2, { match_score: 40 }], [3, { match_score: 70 }]]);
  assert.deepEqual([...rows].sort(collegeSorter('fit', fits, student)).map((row) => row.id), [3, 2, 1]);
});

test('a university is counted under one name per country', () => {
  assert.equal(universityCountry({ country: 'USA' }), 'United States');
  assert.equal(universityCountry({ country: 'Hong Kong SAR, China' }), 'Hong Kong');
  assert.equal(universityCountry({ country: 'Singapore' }), 'Singapore');
});
