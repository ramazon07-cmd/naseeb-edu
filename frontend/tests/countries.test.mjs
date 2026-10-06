import test from 'node:test';
import assert from 'node:assert/strict';
import { countryKey, countryName } from '../src/lib/countries.js';

test('every spelling of a country shares one key, as on the backend', () => {
  assert.equal(countryKey(' USA '), 'us');
  assert.equal(countryKey('United States of America'), 'us');
  assert.equal(countryKey('US'), 'us');
  assert.equal(countryKey('Hong Kong SAR, China'), 'hong kong');
  assert.equal(countryKey('HK'), 'hong kong');
  assert.equal(countryKey('China (Mainland)'), 'china');
  assert.equal(countryKey('Türkiye'), 'turkey');
  assert.equal(countryKey('Singapore'), 'singapore');
  assert.equal(countryKey(null), '');
});

test('aliases display under the catalogue spelling, other countries keep theirs', () => {
  assert.equal(countryName('USA'), 'United States');
  assert.equal(countryName('UK'), 'United Kingdom');
  assert.equal(countryName('Hong Kong SAR, China'), 'Hong Kong');
  assert.equal(countryName('Viet Nam'), 'Vietnam');
  assert.equal(countryName(' South Korea '), 'South Korea');
  assert.equal(countryName(''), '');
});
