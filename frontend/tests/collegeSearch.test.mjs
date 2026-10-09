import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { COLLEGE_PAGE_SIZES, DEFAULT_COLLEGE_FILTERS, collegeSearchQuery } = await import('../src/lib/college.js');

const query = (options) => Object.fromEntries(new URLSearchParams(collegeSearchQuery(options)));

test('a default search asks for one small page sorted by ranking', () => {
  assert.equal(COLLEGE_PAGE_SIZES[0], 10);
  assert.deepEqual(COLLEGE_PAGE_SIZES, [10, 25, 50, 100]);
  assert.equal(collegeSearchQuery({}), 'sort=ranking&page_size=10');
});

test('only filters that differ from the defaults are sent', () => {
  const filters = { ...DEFAULT_COLLEGE_FILTERS, country: 'United States', price: 'budget', aid: ['offers_merit_aid', 'meets_full_need'], bands: ['reach'], testOptional: true, satFit: true, publicOnly: true };
  assert.deepEqual(query({ query: '  tashkent  ', filters, sort: 'fit', view: 'admissions', pageSize: 25, qsFilters: { region: 'Asia' } }), {
    search: 'tashkent', country: 'United States', price: 'budget', aid: 'offers_merit_aid,meets_full_need', bands: 'reach',
    test_optional: 'true', sat_fit: 'true', public: 'true', sort: 'fit', page_size: '25',
  });
});

test('QS filters apply only in the QS view, and unticking every band is sent as an empty list', () => {
  assert.deepEqual(query({ view: 'qs', qsFilters: { region: 'Europe', size: '' } }), { region: 'Europe', sort: 'ranking', page_size: '10' });
  assert.deepEqual(query({ filters: { ...DEFAULT_COLLEGE_FILTERS, bands: [] } }), { bands: '', sort: 'ranking', page_size: '10' });
});

test('the search is trimmed to what the server accepts', () => {
  assert.equal(query({ query: 'x'.repeat(150) }).search.length, 100);
});
