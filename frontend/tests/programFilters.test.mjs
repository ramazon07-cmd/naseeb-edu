import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PROGRAM_FILTER_DEFAULTS, activeProgramFilterCount, adoptProgramFilterUrl, filterPrograms, hasProgramFilters, programFilterState,
  programFilterWrite, programFiltersQuery, readProgramFilters,
} from '../src/lib/programFilters.js';

const today = '2026-09-25';
const program = (id, fields) => ({ id, title: `Program ${id}`, provider: 'Org', program_type: 'international', category: 'Research', delivery_mode: 'unspecified', eligible_grades: '9,10,11', scholarship_available: false, deadline: null, ...fields });
const catalog = [
  program(1, { title: 'Math Olympiad', category: 'Competition', program_type: 'national', delivery_mode: 'onsite', eligible_grades: '8,9,10' }),
  program(2, { title: 'Summer Research Lab', category: 'Research', scholarship_available: true, deadline: '2026-10-01' }),
  program(3, { title: 'Closed Summit', category: 'Conference', deadline: '2026-01-01', delivery_mode: 'online' }),
  program(4, { title: 'Leadership Camp', category: 'Leadership', program_type: 'national', eligible_grades: '9,10,11,gap', scholarship_available: true, description: 'Youth leaders' }),
  program(5, { title: 'Robotics Research', category: 'Research', eligible_grades: '', deadline: '2026-11-01' }),
];
const run = (filters, options = {}) => filterPrograms(catalog, { ...PROGRAM_FILTER_DEFAULTS, ...filters }, { today, ...options });
const ids = (result) => result.programs.map(({ item }) => item.id);

test('defaults hide only closed programs, open ones first by deadline then title', () => {
  const result = run({});
  assert.deepEqual(ids(result), [2, 5, 4, 1]);
  assert.equal(result.counts.closed, 1);
  assert.deepEqual(ids(run({ open: false })), [2, 5, 4, 1, 3]);
});

test('filters combine with AND', () => {
  assert.deepEqual(ids(run({ type: 'international', category: 'Research' })), [2, 5]);
  assert.deepEqual(ids(run({ type: 'international', category: 'Research', aid: true })), [2]);
  assert.deepEqual(ids(run({ type: 'national', grade: 'gap' })), [4]);
  assert.deepEqual(ids(run({ grade: '8' })), [1]);
  assert.deepEqual(ids(run({ delivery: 'online', open: false })), [3]);
  assert.deepEqual(ids(run({ delivery: 'online' })), []);
  assert.deepEqual(ids(run({ type: 'national', category: 'Research' })), []);
});

test('search matches every word, any order, across the visible fields', () => {
  assert.deepEqual(ids(run({ q: 'research' })), [2, 5]);
  assert.deepEqual(ids(run({ q: 'RESEARCH robotics' })), [5]);
  assert.deepEqual(ids(run({ q: 'youth' })), [4]);
  assert.deepEqual(ids(run({ q: 'research nothing' })), []);
  // JSON keys and ids are not searchable text.
  assert.deepEqual(ids(run({ q: 'title' })), []);
  // Translated text is searchable too; the header query narrows further.
  assert.deepEqual(ids(run({ q: 'tadqiqot' }, { translate: (value) => (value === 'Research' ? 'Tadqiqot' : value), localeTag: 'uz' })), [2, 5]);
  assert.deepEqual(ids(run({ q: 'research' }, { query: 'lab' })), [2]);
});

test('each count is what choosing that option would show', () => {
  const filters = { type: 'international', aid: true };
  const { counts } = run(filters);
  // Type counts ignore the type filter but keep the others (aid, open).
  assert.deepEqual(counts.type, { all: 2, international: 1, national: 1 });
  assert.equal(counts.type.international, ids(run({ ...filters, type: 'international' })).length);
  assert.equal(counts.type.national, ids(run({ ...filters, type: 'national' })).length);
  // Aid count ignores the aid filter but keeps the type.
  assert.equal(counts.aid, 1);
  for (const category of ['Research', 'Competition', 'Leadership']) {
    assert.equal(counts.category[category] || 0, ids(run({ ...filters, category })).length, category);
  }
  for (const grade of ['8', '9', 'gap']) {
    assert.equal(counts.grade[grade] || 0, ids(run({ ...filters, grade })).length, grade);
  }
  const unfiltered = run({ open: false }).counts;
  assert.equal(unfiltered.closed, 1);
  assert.equal(unfiltered.type.all, catalog.length);
});

test('filters read from and write to the URL query', () => {
  const filters = readProgramFilters('?type=national&grade=gap&aid=1&open=0&q=math&category=Competition&lang=ru');
  assert.deepEqual(filters, { q: 'math', type: 'national', category: 'Competition', grade: 'gap', delivery: 'all', aid: true, open: false });
  assert.equal(programFiltersQuery('?lang=ru', filters), '?lang=ru&q=math&type=national&category=Competition&grade=gap&aid=1&open=0');
  assert.deepEqual(readProgramFilters(programFiltersQuery('', filters)), filters);
  assert.equal(programFiltersQuery('?type=national&lang=ru', PROGRAM_FILTER_DEFAULTS), '?lang=ru');
  // Bad values fall back to the defaults.
  assert.deepEqual(readProgramFilters('?type=galactic&grade=99&delivery=teleport&aid=yes&open=maybe&category=%20'), PROGRAM_FILTER_DEFAULTS);
  assert.equal(readProgramFilters(`?q=${'x'.repeat(500)}`).q.length, 100);
});

test('filters follow URL changes both ways without eating half-typed text', () => {
  let state = programFilterState('?type=national');
  assert.equal(state.filters.type, 'national');
  // Typing: the page writes its own query and keeps the untrimmed text.
  state = { ...state, filters: { ...state.filters, q: 'math ' } };
  const written = programFilterWrite(state, '?type=national');
  assert.equal(written, '?type=national&q=math');
  state = { ...state, synced: written };
  assert.equal(adoptProgramFilterUrl(state, written), state);
  assert.equal(programFilterWrite(state, written), null);
  // Back to the previous entry restores its filters.
  state = adoptProgramFilterUrl(state, '?type=national');
  assert.deepEqual(state.filters, { ...PROGRAM_FILTER_DEFAULTS, type: 'national' });
  // A sidebar link to bare /programs clears them.
  state = adoptProgramFilterUrl(state, '');
  assert.deepEqual(state.filters, PROGRAM_FILTER_DEFAULTS);
  assert.equal(programFilterWrite(state, ''), null);
});

test('active filter counts drive the reset button and the badge', () => {
  assert.equal(activeProgramFilterCount(PROGRAM_FILTER_DEFAULTS), 0);
  assert.equal(hasProgramFilters(PROGRAM_FILTER_DEFAULTS), false);
  assert.equal(hasProgramFilters({ ...PROGRAM_FILTER_DEFAULTS, q: '  ' }), false);
  assert.equal(hasProgramFilters({ ...PROGRAM_FILTER_DEFAULTS, q: 'math' }), true);
  assert.equal(activeProgramFilterCount({ ...PROGRAM_FILTER_DEFAULTS, type: 'national', open: false, aid: true }), 3);
});
