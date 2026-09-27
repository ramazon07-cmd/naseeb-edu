import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { joinUniqueParts, locationText } = await import('../src/lib/format.js');

test('a region equal to the country is shown once', () => {
  assert.equal(locationText({ city: 'Yangiyer', state: 'Uzbekistan', country: 'Uzbekistan' }), 'Yangiyer · Uzbekistan');
});

test('repeats are matched trimmed and case-insensitively; the first spelling wins', () => {
  assert.equal(locationText({ city: 'Tashkent', state: ' tashkent ', country: 'UZBEKISTAN' }), 'Tashkent · UZBEKISTAN');
  assert.equal(joinUniqueParts('Samarkand', 'Samarkand region', 'samarkand'), 'Samarkand · Samarkand region');
});

test('empty parts are skipped and distinct parts are kept in order', () => {
  assert.equal(locationText({ city: 'Nukus', state: '', country: 'Uzbekistan' }), 'Nukus · Uzbekistan');
  assert.equal(locationText({ city: 'Andijan', state: 'Andijan Region', country: 'Uzbekistan' }), 'Andijan · Andijan Region · Uzbekistan');
  assert.equal(locationText({}), '');
  assert.equal(locationText(), '');
});
