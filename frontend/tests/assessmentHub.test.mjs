// The Profile Assessment hub follows Naseeb Mind: seven challenges in its order,
// work importance placed freely and averaged, EQ scored on its 1..7 scale.
import test from 'node:test';
import assert from 'node:assert/strict';
import { CHALLENGES, INSTRUMENT_VERSION, WIL_ORDER, scoreChallenge } from '../src/challenges.js';

const by = (key) => CHALLENGES.find((challenge) => challenge.key === key);
const answerAll = (challenge, value) => Object.fromEntries(challenge.items.map((item, index) => [item.id, value(item, index)]));

test('the hub has the seven Naseeb Mind challenges in order, all required', () => {
  assert.deepEqual(CHALLENGES.map((challenge) => challenge.key), ['personality', 'interests', 'values', 'subjects', 'workimportance', 'reasoning', 'eq']);
  assert.deepEqual(CHALLENGES.map((challenge) => challenge.number), [1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(CHALLENGES.filter((challenge) => challenge.optional), []);
  for (const challenge of CHALLENGES) assert.ok(INSTRUMENT_VERSION[challenge.key], challenge.key);
});

test('item ids stay unique across every challenge', () => {
  const ids = CHALLENGES.flatMap((challenge) => challenge.items.map((item) => item.id));
  assert.equal(new Set(ids).size, ids.length);
});

test('work importance accepts any spread and averages each value', () => {
  const challenge = by('workimportance');
  assert.equal(challenge.interaction, undefined);
  // Every card in one level: the old four-per-level sort refused this.
  const flat = scoreChallenge(challenge, answerAll(challenge, () => 5));
  assert.ok(flat);
  for (const value of WIL_ORDER) assert.equal(flat.scores[value], 5);

  const leaning = scoreChallenge(challenge, answerAll(challenge, (item) => (item.value === 'independence' ? 5 : 2)));
  assert.equal(leaning.ranked[0], 'independence');
  assert.equal(leaning.scores.achievement, 2);
});

test('EQ scores four unweighted means on 1..7 and needs every item', () => {
  const challenge = by('eq');
  assert.equal(challenge.items.length, 16);
  assert.equal(challenge.scale.length, 7);
  const result = scoreChallenge(challenge, answerAll(challenge, (item) => ({ SEA: 7, OEA: 1, UOE: 4, ROE: 6 })[item.dim]));
  assert.deepEqual(result.scores, { SEA: 7, OEA: 1, UOE: 4, ROE: 6 });
  assert.deepEqual(result.ranked, ['SEA', 'ROE', 'UOE', 'OEA']);

  const partial = answerAll(challenge, () => 4);
  delete partial[challenge.items[15].id];
  assert.equal(scoreChallenge(challenge, partial), null);
});
