import test from 'node:test';
import assert from 'node:assert/strict';
import { ieltsOverall, satSentTotal, testScoresFromProfile, testScoresPayload, validateTestScores } from '../src/lib/testScores.js';

const today = new Date(2026, 8, 25);
const ielts = { ielts_status: 'taken', ielts_score: '6.5', ielts_listening: '7', ielts_reading: '6.5', ielts_writing: '6', ielts_speaking: '6.5', ielts_test_date: '2026-03-14', ielts_attempts: '2' };
const sat = { sat_status: 'taken', sat_reading: '650', sat_math: '700', sat_test_date: '2026-05-02', sat_attempts: '1', sat_superscore: null };
const keys = (form) => Object.keys(validateTestScores(form, today)).sort();

test('IELTS overall follows the official half-band rounding', () => {
  assert.equal(ieltsOverall([6.5, 6.5, 5, 7]), 6.5); // 6.25 rounds up
  assert.equal(ieltsOverall([7, 7, 7, 6.5]), 7); // 6.875 -> 7
  assert.equal(ieltsOverall([6, 6, 6, 6.5]), 6); // 6.125 -> 6
  assert.equal(ieltsOverall([6.5, 6.5, 6, 6]), 6.5); // 6.25 -> 6.5
  assert.equal(ieltsOverall([7, '', 6, 6]), null);
});

test('a complete, consistent answer passes', () => {
  assert.deepEqual(keys({ ...ielts, ...sat }), []);
  assert.deepEqual(keys({ ielts_status: 'not_taken', sat_status: 'not_required' }), []);
});

test('IELTS rules: overall must match sections, sections all-or-none, past test date', () => {
  assert.deepEqual(validateTestScores({ ...ielts, ielts_score: '7.5' }, today).ielts_score, ['With these section scores your overall band is {0}. Check your test report.', 6.5]);
  assert.deepEqual(keys({ ...ielts, ielts_speaking: '' }), ['ielts_speaking']);
  assert.deepEqual(keys({ ielts_status: 'taken', ielts_test_date: '2026-01-01' }), ['ielts_score']);
  assert.deepEqual(keys({ ...ielts, ielts_test_date: '2026-10-01' }), ['ielts_test_date']);
  assert.deepEqual(keys({ ...ielts, ielts_test_date: '' }), ['ielts_test_date']);
  assert.deepEqual(keys({ ...ielts, ielts_attempts: '0' }), ['ielts_attempts']);
  assert.deepEqual(keys({ ...ielts, ielts_attempts: '1.5' }), ['ielts_attempts']);
  assert.deepEqual(keys({ ielts_status: 'scheduled' }), ['ielts_test_date']);
  assert.deepEqual(keys({ ielts_status: 'planning' }), []);
  assert.deepEqual(keys({ ielts_status: 'planning', ielts_test_date: '2014-05-01' }), ['ielts_test_date']);
});

test('SAT rules: 200-800 in steps of 10, superscore only after two attempts', () => {
  assert.deepEqual(keys({ ...sat, sat_reading: '655' }), ['sat_reading']);
  assert.deepEqual(keys({ ...sat, sat_math: '900' }), ['sat_math']);
  assert.deepEqual(keys({ ...sat, sat_math: '' }), ['sat_math']);
  assert.deepEqual(keys({ ...sat, sat_superscore: true }), [], 'one attempt: superscore is ignored');
  assert.deepEqual(keys({ ...sat, sat_attempts: '2' }), ['sat_superscore']);
  assert.deepEqual(keys({ ...sat, sat_attempts: '2', sat_superscore: false }), []);
  assert.deepEqual(keys({ ...sat, sat_attempts: '2', sat_superscore: true }), ['sat_superscore_math', 'sat_superscore_reading']);
  assert.deepEqual(keys({ ...sat, sat_attempts: '2', sat_superscore: true, sat_superscore_reading: '640', sat_superscore_math: '720' }), ['sat_superscore_reading']);
});

test('AP and IB rows need a subject and a score in range', () => {
  const subjects = [{ type: 'AP', subject: 'Biology', score: '5' }, { type: 'AP', subject: '', score: '6' }, { type: 'IB', subject: 'Physics HL', score: '7' }, { type: 'IB', subject: 'Maths', score: '' }];
  assert.deepEqual(keys({ subjects }), ['subjects.1.score', 'subjects.1.subject', 'subjects.3.score']);
});

test('payload computes totals and drops superscore when it does not apply', () => {
  const payload = testScoresPayload({ ...ielts, ielts_score: '', ...sat, sat_superscore: true, subjects: [{ type: 'AP', subject: ' Biology ', score: '4' }] });
  assert.equal(payload.ielts_score, 6.5);
  assert.equal(payload.sat_superscore, null);
  assert.equal(payload.sat_reading, 650);
  assert.deepEqual(payload.subjects, [{ type: 'AP', subject: 'Biology', score: 4 }]);
  assert.equal(satSentTotal({ ...sat, sat_superscore: true, sat_superscore_reading: '690', sat_superscore_math: '720' }), 1410);
  assert.equal(satSentTotal(sat), 1350);
});

test('profile data maps back into form answers', () => {
  const form = testScoresFromProfile({ ielts_status: 'taken', ielts_score: '6.5', ielts_listening: '7.0', sat_status: 'not_taken', sat_score: null, sat_superscore: null });
  assert.equal(form.ielts_listening, '7');
  assert.equal(form.ielts_score, '6.5');
  assert.equal(form.sat_superscore, null);
  assert.equal(testScoresFromProfile({ ielts_score: '7.0', sat_score: 1400 }).sat_status, 'taken');
});
