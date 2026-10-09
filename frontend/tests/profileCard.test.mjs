import test from 'node:test';
import assert from 'node:assert/strict';
import { profileCardData, wrapLines } from '../src/lib/profileCard.js';

const interests = [{ scoring: 'riasec' }, { means: { R: 1.5, I: 4.2, A: 3.8, S: 4.6, E: 2, C: 2.4 }, code: ['S', 'I', 'A'] }];
const personality = [{ scoring: 'bigfive' }, { ES: 3.2, E: 4, O: 4.5, A: 3.6, C: 4.1 }];
const subjects = [{ scoring: 'subjects' }, { ranked: ['biology', 'chemistry', 'english', 'art'], bySubject: {} }];
const reasoning = [{ scoring: 'icar' }, { correct: 13, total: 16 }];

test('the card waits for Interests and shows only what is finished', () => {
  assert.equal(profileCardData({ results: [personality, [{ scoring: 'riasec' }, null]], majors: null, firstName: 'Ramazon' }), null);
  const card = profileCardData({ results: [interests, [{ scoring: 'bigfive' }, null], subjects], majors: null, firstName: 'Ramazon' });
  assert.deepEqual(card.code.map((item) => item.letter), ['S', 'I', 'A']);
  assert.deepEqual(card.interests.filter((item) => item.top).map((item) => item.letter), ['I', 'A', 'S']);
  assert.equal(card.traits, null);
  assert.equal(card.subjects.length, 3);
  assert.equal(card.majors, null, 'majors stay off while recommendations are locked');
});

test('the card never carries the reasoning score or identity-document data', () => {
  const card = profileCardData({ results: [interests, personality, subjects, reasoning], majors: ['Biology', 'Psychology', 'Medicine', 'Chemistry'], firstName: 'Ramazon', lastName: 'Ergashev', date: new Date(2026, 9, 8) });
  assert.deepEqual(Object.keys(card).sort(), ['code', 'date', 'firstName', 'interests', 'lastName', 'majors', 'name', 'subjects', 'traits']);
  assert.equal(card.name, 'Ramazon Ergashev');
  assert.equal(card.date, '08.10.2026');
  assert.equal(card.majors.length, 3);
  assert.equal(card.traits.length, 5);
  assert.ok(!JSON.stringify(card).includes('13'));
});

// Every character is 10 px wide.
const ctx = { measureText: (text) => ({ width: text.length * 10 }) };

test('text wraps at the width and ends in an ellipsis when cut', () => {
  assert.deepEqual(wrapLines(ctx, 'Helping people and leading', 150), ['Helping people', 'and leading']);
  assert.deepEqual(wrapLines(ctx, 'Helping people and leading', 150, 1), ['Helping people…']);
  assert.deepEqual(wrapLines(ctx, 'Biotechnologyengineering', 100), ['Biotechno…']);
  assert.deepEqual(wrapLines(ctx, '', 100), []);
});
