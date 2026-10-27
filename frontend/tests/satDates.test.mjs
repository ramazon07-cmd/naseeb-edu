import test from 'node:test';
import assert from 'node:assert/strict';
import { SAT_WEEKEND_DATES, satTestDates } from '../src/lib/satDates.js';
import { testScoresFromProfile, testScoresPayload, validateTestScores } from '../src/lib/testScores.js';

test('SAT options use published administrations, including the actual September date', () => {
  assert.ok(SAT_WEEKEND_DATES.includes('2026-09-12'));
  assert.ok(SAT_WEEKEND_DATES.includes('2026-05-02'));
  assert.ok(!SAT_WEEKEND_DATES.includes('2026-09-19'));
  assert.ok(!SAT_WEEKEND_DATES.includes('2026-04-04'));
  assert.ok(!SAT_WEEKEND_DATES.includes('2027-08-28'), 'Anticipated dates are not confirmed options');
  assert.deepEqual(SAT_WEEKEND_DATES, [...new Set(SAT_WEEKEND_DATES)].sort());
});

test('score entries offer past SAT dates, newest first; bookings offer future dates, soonest first', () => {
  const past = satTestDates('taken', '2026-10-20');
  assert.equal(past[0], '2026-10-03');
  assert.ok(past.every((date) => date <= '2026-10-20'));
  assert.deepEqual(past, [...past].sort().reverse());
  const upcoming = satTestDates('scheduled', '2026-10-20');
  assert.deepEqual(upcoming, ['2026-11-07', '2026-12-05', '2027-03-06', '2027-05-01', '2027-06-05']);
  assert.deepEqual(satTestDates('planning', '2026-10-20'), upcoming);
  assert.deepEqual(satTestDates('not_taken', '2026-10-20'), []);
});

test('SAT options include test day itself and update across the local day boundary', () => {
  assert.ok(!satTestDates('taken', '2026-05-01').includes('2026-05-02'));
  assert.equal(satTestDates('taken', '2026-05-02')[0], '2026-05-02');
  assert.equal(satTestDates('scheduled', '2026-05-02')[0], '2026-05-02');
  assert.equal(satTestDates('scheduled', '2026-05-03')[0], '2026-06-06');
});

test('documented special sessions and older saved dates round-trip without a silent date correction', () => {
  for (const sat_test_date of ['2026-09-19', '2026-10-04', '2023-11-04']) {
    const form = { sat_status: 'taken', sat_reading: '800', sat_math: '670', sat_attempts: '1', sat_test_date };
    assert.deepEqual(validateTestScores(form, new Date(2026, 9, 20)), {});
    const payload = testScoresPayload(form);
    assert.equal(payload.sat_test_date, sat_test_date);
    assert.equal(testScoresFromProfile(payload).sat_test_date, sat_test_date);
  }
});
