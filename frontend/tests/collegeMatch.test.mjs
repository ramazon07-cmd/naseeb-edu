import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const {
  addAllBusy, applicationProgram, beginReasons, bulkAddTier, costText, failReasons, finishReasons, idleReasons,
  idleMatch, individualAddBusy, invalidateMatch, matchMessage, reasonsKey, reasonsView, satPositionText, subjectRankText,
} = await import('../src/lib/collegeMatch.js');

test('a subject rank reads "#12 in Computer Science, QS 2026" and keeps a published range', () => {
  const subject = { name: 'Computer Science & Information Systems', year: 2026, rank_label: '12' };
  assert.equal(subjectRankText(subject), '#12 in Computer Science & Information Systems, QS 2026');
  assert.equal(subjectRankText({ ...subject, rank_label: '201-250' }), '#201-250 in Computer Science & Information Systems, QS 2026');
  assert.equal(subjectRankText({ name: 'Law', rank_label: null }), 'No QS rank in Law');
  assert.equal(subjectRankText({ overall: true, rank_label: '5' }), 'Overall QS rank #5');
  assert.equal(subjectRankText(null), '');
});

test('the SAT position names the student score and the range', () => {
  assert.equal(satPositionText({ position: 'below', score: 1450, min: 1520, max: 1580 }), 'SAT 1450: below the usual range (1520–1580)');
  assert.equal(satPositionText({ position: 'inside', score: 1300, min: 1200, max: 1400 }), 'SAT 1300: inside the usual range (1200–1400)');
  assert.equal(satPositionText({ position: 'above', score: 1500, min: 1200, max: 1400 }), 'SAT 1500: above the usual range (1200–1400)');
  assert.equal(satPositionText({ position: 'inside', score: 1300, min: 1200, max: null }), 'SAT 1300: inside the usual range (1200+)');
  assert.equal(satPositionText({ position: 'no_range' }), 'No SAT range listed');
});

test('cost against the budget and server notes', () => {
  assert.match(costText({ cost_vs_budget: 'within', budget_usd: 30000 }), /^Within your budget of/);
  assert.match(costText({ cost_vs_budget: 'over', budget_usd: 30000 }), /^Over your budget of/);
  assert.equal(costText({ cost_vs_budget: 'unknown', budget_usd: 30000 }), 'Cost unknown');
  assert.equal(matchMessage({ code: 'pick_major', text: 'x' }), 'Pick your major for a better list');
  assert.equal(matchMessage({ code: 'short_list', params: { count: 7 }, text: 'x' }), 'Only 7 universities fit your profile and budget.');
  assert.equal(matchMessage({ code: 'other', text: 'Plain text' }), 'Plain text');
});

test('an application is filed under the suggested program, then the matcher, then the typed major', () => {
  const university = { suggested_programs: [{ name: 'BSc Computer Science', canonical_major: 'Computer Science' }], programs: [] };
  assert.equal(applicationProgram(university, 'информатика'), 'BSc Computer Science');
  const plain = { suggested_programs: [], programs: [{ name: 'BSc Data', canonical_major: 'Data' }] };
  assert.equal(applicationProgram(plain, 'data'), 'BSc Data');
  assert.equal(applicationProgram(plain, 'информатика'), 'информатика');
  assert.equal(applicationProgram({}, ''), 'Undeclared');
});

test('explanations belong to one match generation and language', () => {
  const first = reasonsKey(1, 'en');
  let state = finishReasons(beginReasons(idleReasons(first), first), first, { 7: 'Fits' });
  assert.deepEqual(reasonsView(state, first).lines, { 7: 'Fits' });
  assert.equal(reasonsView(state, first).status, 'done');
  for (const key of [reasonsKey(2, 'en'), reasonsKey(1, 'uz')]) {
    assert.equal(reasonsView(state, key).status, 'idle');
    assert.deepEqual(reasonsView(state, key).lines, {});
  }
  const second = reasonsKey(2, 'en');
  state = beginReasons(state, second);
  assert.deepEqual(state.lines, {});
  assert.equal(finishReasons(state, first, { 7: 'Old' }), state);
  assert.equal(failReasons(state, first, 'late'), state);
  assert.equal(finishReasons(state, second, { 8: 'New' }).lines[8], 'New');
});

test('Add and Add all never run together, and Add all skips what is already listed', () => {
  assert.equal(individualAddBusy({ busyId: null, addingAll: true }, 5), true);
  assert.equal(individualAddBusy({ busyId: 5, addingAll: false }, 5), true);
  assert.equal(individualAddBusy({ busyId: 5, addingAll: false }, 6), false);
  assert.equal(addAllBusy({ busyId: 5, addingAll: false }), true);
  assert.equal(addAllBusy({ busyId: null, addingAll: true }), true);
  assert.equal(addAllBusy({ busyId: null, addingAll: false }), false);
  const tiers = { reach: 'reach', safety: 'safety' };
  const listed = new Map([[1, {}]]);
  assert.equal(bulkAddTier({ id: 1, fit: { admission_band: 'reach' } }, listed, tiers), null);
  assert.equal(bulkAddTier({ id: 2, fit: { admission_band: 'safety' } }, listed, tiers), 'safety');
  assert.equal(bulkAddTier({ id: 3, fit: {} }, listed, tiers), null);
});

test('refreshing the research profile invalidates the stored match and pending responses', () => {
  const stored = { loading: false, data: { universities: [{ id: 1, fit: 'target' }] }, error: '', generation: 3 };
  const fresh = invalidateMatch(stored.generation);
  assert.deepEqual(fresh, idleMatch(4));
  assert.equal(fresh.data, null);
  assert.notEqual(fresh.generation, stored.generation);
  assert.notEqual(reasonsKey(fresh.generation, 'en'), reasonsKey(stored.generation, 'en'));
  assert.equal(invalidateMatch(fresh.generation).generation, 5);
});
