import test from 'node:test';
import assert from 'node:assert/strict';
import { coachSource, criteriaRows, criterionLabel, isCached, kindOf, noteForQuote, overallScore, resultMode, rubricName, safetyContent, scoreBand } from '../src/essayLab/coachModel.js';

test('overall depth score averages the five 1-4 scores', () => {
  const overall = overallScore({scores: {reflection: 2, specificity: 2, voice: 3, structure: 3, prompt_fit: 3}});
  assert.equal(overall.percent, 65);
  assert.equal(overall.band.label, 'Developing');
  assert.equal(overallScore({}), null);
  assert.equal(overallScore({scores: {reflection: 9, voice: 4}}).percent, 100, 'out-of-range values are ignored');
});

test('score bands and note kinds', () => {
  assert.equal(scoreBand(4).label, 'Excellent');
  assert.equal(scoreBand(3).label, 'Strong');
  assert.equal(scoreBand(2).label, 'Developing');
  assert.equal(scoreBand(1).label, 'Getting started');
  assert.equal(scoreBand(null).label, 'Not scored');
  assert.equal(kindOf({kind: 'specific'}).tab, 'Specifics');
  assert.equal(kindOf({kind: 'unknown'}).id, 'reflect');
});

test('coach source tells built-in rule checks apart from AI checks', () => {
  assert.equal(coachSource(null), null);
  assert.equal(coachSource({model: 'local'}), 'rules');
  assert.equal(coachSource({model: ''}), 'rules', 'a check without a model name is never presented as AI');
  assert.equal(coachSource({}), 'rules');
  assert.equal(coachSource({model: 'openai/gpt-5-mini'}), 'ai');
});

test('old-shape results (no rubric_version, no overall) keep legacy labels and averaged score', () => {
  const result = {scores: {reflection: 2, specificity: 2, voice: 3, structure: 3, prompt_fit: 3}, notes: []};
  assert.deepEqual(criteriaRows(result).map((row) => row.label), ['Reflection', 'Specific details', 'Your voice', 'Structure', 'Answers the question']);
  assert.equal(overallScore(result).percent, 65);
  assert.equal(overallScore({scores: {}}), null);
  assert.equal(rubricName(result), '');
});

test('personal statement and supplement render their own criteria keys', () => {
  const personal = {type: 'personal_statement', rubric_version: 2, overall: 63, scores: {reflection: 3, specificity: 2, voice: 3, structure: 2, prompt_fit: 3}};
  assert.deepEqual(criteriaRows(personal).map((row) => row.key), ['reflection', 'specificity', 'voice', 'structure', 'prompt_fit']);
  assert.equal(criteriaRows(personal)[0].label, 'Reflection and insight');
  const supplement = {type: 'supplement', rubric_version: 2, overall: 50, scores: {fit_specificity: 2, reflection: 3, evidence: 2, voice: 3, concision: 4}};
  const rows = criteriaRows(supplement);
  assert.deepEqual(rows.map((row) => row.key), ['fit_specificity', 'reflection', 'evidence', 'voice', 'concision']);
  assert.equal(rows[0].label, 'Specificity to the school, program or prompt');
  assert.equal(rows[4].value, 4);
  assert.equal(rubricName(supplement), 'Supplemental essay');
  assert.equal(rubricName({type: 'scholarship'}), 'Scholarship essay');
  assert.equal(criteriaRows({type: 'free_writing', rubric_version: 3, scores: {clarity_idea: 3}})[0].label, 'Clarity of the central idea');
  assert.equal(criteriaRows({type: 'scholarship', rubric_version: 3, scores: {goals_impact: 3, mission_fit: 2}})[1].label, 'Fit to the scholarship’s mission');
  assert.equal(rubricName({type: 'free_writing'}), 'Free writing');
});

test('server overall (0-100) wins over local averaging', () => {
  const overall = overallScore({type: 'supplement', rubric_version: 2, overall: 100, scores: {evidence: 1}});
  assert.equal(overall.percent, 100);
  assert.equal(overall.band.label, 'Excellent');
  assert.equal(overallScore({overall: 0, scores: {voice: 4}}).percent, 0);
});

test('unknown criteria keys fall back to a label made from the key and bad values are skipped', () => {
  const rows = criteriaRows({type: 'scholarship', rubric_version: 1, scores: {need_story: 3, community_impact: 2, bogus: 7, zero: 0, frac: 2.5}});
  assert.deepEqual(rows.map((row) => [row.key, row.label]), [['need_story', 'Need story'], ['community_impact', 'Community impact']]);
  assert.equal(criterionLabel('mystery', 'long_term_goal'), 'Long term goal');
  assert.equal(criteriaRows({type: 'x', rubric_version: 1, scores: null}).length, 0);
});

test('evidence quotes attach to criteria and can be matched to a note for highlighting', () => {
  const result = {type: 'personal_statement', rubric_version: 2, scores: {voice: 3, reflection: 1}, score_evidence: {voice: 'I sold the last  bread', reflection: 5}};
  const rows = criteriaRows(result);
  assert.equal(rows[0].evidence, 'I sold the last  bread');
  assert.equal(rows[1].evidence, '');
  const notes = [{id: 'n1', quote: 'I sold the last bread'}, {id: 'n2', quote: 'other words'}];
  assert.equal(noteForQuote(notes, 'i sold the LAST  bread').id, 'n1');
  assert.equal(noteForQuote(notes, 'not there'), null);
  assert.equal(noteForQuote(notes, ''), null);
});

test('safety mode carries no criteria and exposes message and resources', () => {
  const check = {result: {mode: 'safety', message: 'You are not alone.', resources: ['Helpline 1234', {label: 'Child line', text: '5678'}]}};
  assert.equal(resultMode(check), 'safety');
  assert.equal(resultMode({result: {mode: 'score'}}), 'check');
  assert.equal(resultMode({result: {}}), 'check');
  assert.equal(resultMode(null), 'check');
  const content = safetyContent(check.result);
  assert.equal(content.message, 'You are not alone.');
  assert.deepEqual(content.resources, [{label: '', text: 'Helpline 1234'}, {label: 'Child line', text: '5678'}]);
  assert.deepEqual(safetyContent({message: 'x', resource: 'Call 1'}).resources, [{label: '', text: 'Call 1'}]);
  assert.deepEqual(safetyContent({}), {message: '', resources: []});
  assert.equal(criteriaRows(check.result).length, 0);
});

test('cached flag is read from the check or its result', () => {
  assert.equal(isCached({cached: true}), true);
  assert.equal(isCached({result: {cached: true}}), true);
  assert.equal(isCached({cached: false, result: {}}), false);
  assert.equal(isCached(null), false);
});
