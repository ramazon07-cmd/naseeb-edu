import test from 'node:test';
import assert from 'node:assert/strict';
import { SCORE_HIDDEN_TEXT, criteriaFor, explainFor, nearBandEdge, normalizeCheck } from '../src/essayLab/coachModel.js';
import { ESSAY_LAB_TRANSLATIONS } from '../src/translations/essayLab.js';

test('near a band edge (within 3 points of 50, 60, 70 or 80) the panel says so', () => {
  for (const edge of [50, 60, 70, 80]) {
    for (const offset of [-3, -2, -1, 0, 1, 2, 3]) assert.equal(nearBandEdge(edge + offset), true, `${edge + offset}`);
  }
  for (const far of [0, 20, 40, 46, 54, 56, 64, 66, 74, 76, 84, 90, 100]) assert.equal(nearBandEdge(far), false, `${far}`);
  assert.equal(nearBandEdge(null), false);
  assert.equal(nearBandEdge(undefined), false);
  assert.equal(nearBandEdge('x'), false);
  assert.equal(nearBandEdge('51'), true);
});

test('the supplement rubric shows its fifth criterion as Focus and length', () => {
  const personal = criteriaFor('personal_statement');
  const supplement = criteriaFor('supplement');
  assert.equal(personal.find((item) => item.key === 'structure').label, 'Structure');
  assert.equal(criteriaFor(null).find((item) => item.key === 'structure').label, 'Structure', 'old checks keep Structure');
  assert.equal(supplement.find((item) => item.key === 'structure').label, 'Focus and length');
  assert.deepEqual(supplement.map((item) => item.key), personal.map((item) => item.key));
  assert.deepEqual(supplement.filter((item) => item.key !== 'structure'), personal.filter((item) => item.key !== 'structure'));
  assert.equal(explainFor('supplement', 'structure', { structure: 'x' }) !== 'x', true);
  assert.equal(explainFor('personal_statement', 'structure', { structure: 'x' }), 'x');
});

test('every new line of text has Uzbek and Russian', () => {
  for (const key of [
    'Close to the next level', 'Focus and length', 'Take care', 'You are not alone in this', 'Helpline',
    'Does it use the space well, with no sentence that only repeats?',
    'If writing about this was hard, your counselor is there to talk, whenever you want.',
    'No question was given, so fit to the question counts as Solid (3). Add the school’s question to have it judged.',
    'What you wrote sounds heavy, so Naseeb AI has not scored this essay. Please talk to your counselor or to someone you trust. Telling them is your choice, and you can go at your own pace.',
  ]) {
    const value = ESSAY_LAB_TRANSLATIONS[key];
    assert.ok(Array.isArray(value) && value.length === 2 && value.every((item) => item && item !== key), key);
  }
});

const check = (result) => ({ result: { version: 2, scored: true, overall: 60, scores: {}, notes: [], ...result } });

test('the safety flag, helpline and fit default are read from the result', () => {
  const danger = normalizeCheck(check({ scored: false, overall: null, safety: 'current_danger', helpline: ' Call 000 ', notes_locked: true }));
  assert.equal(danger.scored, false);
  assert.equal(danger.safety, 'current_danger');
  assert.equal(danger.helpline, 'Call 000');
  const noNumber = normalizeCheck(check({ scored: false, overall: null, safety: 'current_danger', helpline: '' }));
  assert.equal(noNumber.helpline, '', 'an empty setting shows no number');
  assert.equal(normalizeCheck(check({ safety: 'past_hardship' })).safety, 'past_hardship');
  assert.equal(normalizeCheck(check({ safety: 'bogus' })).safety, null);
  assert.equal(normalizeCheck(check({})).safety, null);
  assert.equal(normalizeCheck(check({ fit_default: true, rubric: 'supplement' })).fitDefault, true);
  assert.equal(normalizeCheck(check({ rubric: 'supplement' })).rubric, 'supplement');
  assert.equal(normalizeCheck({ result: { scores: { voice: 3 }, notes: [], safety: 'current_danger' } }).safety, null, 'old checks have no safety flag');
});

test('a hidden score and a length failure are read from the result', () => {
  const short = normalizeCheck(check({ scored: false, overall: null, scores: {}, score_hidden: 'short' }));
  assert.equal(short.scored, false);
  assert.equal(short.scoreHidden, 'short');
  assert.equal(normalizeCheck(check({ scored: false, overall: null, score_hidden: 'calibrating' })).scoreHidden, 'calibrating');
  assert.equal(normalizeCheck(check({ score_hidden: 'bogus' })).scoreHidden, null);
  assert.equal(normalizeCheck(check({})).scoreHidden, null);
  assert.equal(normalizeCheck(check({ length: 'over_limit' })).length, 'over_limit');
  assert.equal(normalizeCheck(check({ length: 'ok' })).length, null);
  assert.deepEqual(Object.keys(SCORE_HIDDEN_TEXT).sort(), ['calibrating', 'short']);
  for (const key of [
    ...Object.values(SCORE_HIDDEN_TEXT),
    'This essay is over its word limit, so “Answers the prompt” counts as 1.',
    'A Common App essay needs at least 250 words, so “Answers the prompt” counts as 1.',
  ]) {
    const value = ESSAY_LAB_TRANSLATIONS[key];
    assert.ok(Array.isArray(value) && value.length === 2 && value.every((item) => item && item !== key), key);
  }
});
