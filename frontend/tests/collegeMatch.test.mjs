import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const {
  academicStanding, addAllBusy, applicationProgram, matchFootnote, beginReasons, bulkAddTier, costText, failReasons, finishReasons, idleReasons,
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
  assert.equal(satPositionText({ position: 'act_used', score: 31, min: 1200, max: 1400 }), 'Compared using your ACT 31');
});

test('academic standing: below 0, the middle 50% up to 1, above from 1', () => {
  assert.equal(academicStanding(null), null);
  assert.equal(academicStanding(undefined), null);
  assert.equal(academicStanding(-0.01), 'Below most admitted students');
  assert.equal(academicStanding(0), 'Inside the middle 50%');
  assert.equal(academicStanding(0.99), 'Inside the middle 50%');
  assert.equal(academicStanding(1), 'Above most admitted students');
  assert.equal(academicStanding(1.5), 'Above most admitted students');
});

test('the footnote names the ranking used and the AI lines only when shown', () => {
  const bySubject = matchFootnote({ subjects: [{ code: 'COM02' }] }, false);
  assert.match(bySubject, /QS subject rankings 2026/);
  assert.doesNotMatch(bySubject, /Naseeb AI/);
  const overall = matchFootnote({ subjects: [] }, true);
  assert.match(overall, /overall QS World University Rankings 2027/);
  assert.doesNotMatch(overall, /subject rankings/);
  assert.match(overall, /Why these fit you lines are written by Naseeb AI from these facts only\.$/);
});

test('cost against the budget and server notes', () => {
  assert.match(costText({ cost_vs_budget: 'within', budget_usd: 30000 }), /^Within your budget of/);
  assert.match(costText({ cost_vs_budget: 'over', budget_usd: 30000 }), /^Over your budget of/);
  assert.equal(costText({ cost_vs_budget: 'unknown', budget_usd: 30000 }), 'Cost unknown');
  assert.equal(matchMessage({ code: 'pick_major', text: 'x' }), 'Pick your major for a better list');
  assert.equal(matchMessage({ code: 'short_list', params: { count: 7 }, text: 'x' }), 'Only 7 universities fit your profile and budget.');
  assert.equal(matchMessage({ code: 'other', text: 'Plain text' }), 'Plain text');
  assert.equal(matchMessage({ code: 'test_needed', params: { count: 3 }, text: 'x' }),
    '3 universities were left out because they expect an SAT or ACT score; add yours to see them.');
  assert.equal(matchMessage({ code: 'aid_unknown', params: { count: 2 }, text: 'x' }), '2 universities were left out: the catalogue has no aid details.');
  assert.equal(matchMessage({ code: 'no_intl_aid', params: { count: 1 }, text: 'x' }), '1 universities were left out: they list no aid for students from abroad.');
  assert.equal(matchMessage({ code: 'filled_from', params: { group: 'reach', from: 'safety', count: 2 }, text: 'x' }).endsWith('group were added.'), true);
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
