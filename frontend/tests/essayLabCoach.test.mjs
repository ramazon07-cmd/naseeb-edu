import test from 'node:test';
import assert from 'node:assert/strict';
import { coachSource, kindOf, overallScore, scoreBand } from '../src/essayLab/coachModel.js';

test('overall depth score averages the five 1-4 scores', () => {
  const overall = overallScore({reflection: 2, specificity: 2, voice: 3, structure: 3, prompt_fit: 3});
  assert.equal(overall.percent, 65);
  assert.equal(overall.band.label, 'Developing');
  assert.equal(overallScore({}), null);
  assert.equal(overallScore({reflection: 9, voice: 4}).percent, 100, 'out-of-range values are ignored');
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
