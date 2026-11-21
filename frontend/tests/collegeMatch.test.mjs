import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { costText, matchMessage, satPositionText, subjectRankText } = await import('../src/lib/collegeMatch.js');

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
