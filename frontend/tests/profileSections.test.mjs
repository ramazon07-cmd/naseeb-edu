import test from 'node:test';
import assert from 'node:assert/strict';
import { PROFILE_SECTIONS, answersPayload, listText, profileAnswers, readinessHints, sectionByKey, validateSection } from '../src/lib/profileSections.js';
import { ONBOARDING_STEP_FIELDS } from '../src/lib/onboardingDraft.js';

const profile = {
  id: 7, grade: '11', school_name: 'Presidential School', gpa: '4.60', gpa_scale: 5, target_countries: 'USA, Canada, Singapore',
  guardian_name: 'Dilnoza', guardian_relation: 'mother', parent_contact: '+998901112233',
  user_detail: { first_name: 'Ramazon', last_name: 'Ergashev' },
  ielts_status: 'taken', ielts_score: '7.0', ielts_listening: '7.5', ielts_reading: '7.0', ielts_writing: '6.5', ielts_speaking: '7.0', ielts_attempts: 2, ielts_test_date: '2026-03-14',
  sat_status: 'planning', sat_test_date: '2026-11-01',
  application_profile: { gender: 'Male', city: 'Tashkent', class_size: 25, interests: ['Engineering'], subjects: [{ type: 'AP', subject: 'Biology', score: 5 }], ielts_score: '6.0' },
};

test('every onboarding question belongs to exactly one section', () => {
  assert.deepEqual(PROFILE_SECTIONS.map((section) => section.key), ['personal', 'academics', 'tests', 'goal', 'honors', 'activities']);
  const all = PROFILE_SECTIONS.flatMap((section) => section.fields);
  assert.equal(new Set(all).size, all.length);
  assert.deepEqual(new Set(all), new Set(ONBOARDING_STEP_FIELDS.flat().filter((name) => name !== 'photo')));
});

test('saved answers fill the form; columns win over the old JSON copy', () => {
  const form = profileAnswers(profile);
  assert.equal(form.first_name, 'Ramazon');
  assert.equal(form.gpa_scale, '5');
  assert.equal(form.ielts_score, '7');
  assert.equal(form.guardian_contact, '+998901112233');
  assert.deepEqual(form.target_countries, ['US', 'Canada']);
  assert.deepEqual(form.subjects, [{ type: 'AP', subject: 'Biology', score: '5' }]);
  assert.deepEqual(form.honors, []);
});

test('a section payload holds only that section, typed for the API', () => {
  const form = { ...profileAnswers(profile), class_rank: '3', gpa: '4.7' };
  assert.deepEqual(answersPayload(form, 'goal'), { target_countries: 'US, Canada', interests: ['Engineering'], program_strengths: [] });
  const academics = answersPayload(form, 'academics');
  assert.deepEqual(Object.keys(academics).sort(), [...sectionByKey('academics').fields].filter((name) => name in academics).sort());
  assert.equal(academics.gpa, 4.7);
  assert.equal(academics.class_rank, 3);
  assert.ok(!('first_name' in academics));
  const tests = answersPayload(form, 'tests');
  assert.equal(tests.ielts_listening, 7.5);
  assert.equal(tests.sat_superscore, null);
  assert.deepEqual(tests.subjects, [{ type: 'AP', subject: 'Biology', score: 5 }]);
  assert.ok(!('city' in tests));
  // Without a section: everything, as onboarding sends it.
  assert.equal(answersPayload(form).city, 'Tashkent');
});

test('section checks run before saving', () => {
  const form = profileAnswers(profile);
  assert.deepEqual(validateSection('goal', { ...form, target_countries: [] }), { target_countries: ['Select at least one country.'] });
  assert.deepEqual(Object.keys(validateSection('tests', { ...form, ielts_listening: '9' }, new Date(2026, 8, 25))), ['ielts_score']);
  assert.deepEqual(validateSection('personal', form), {});
});

test('the readiness hint names the first missing items in the order given', () => {
  const readiness = { percent: 58, missing: [{ key: 'sat', section: 'tests' }, { key: 'unknown', section: 'x' }, { key: 'activities', section: 'activities' }, { key: 'honors', section: 'honors' }] };
  assert.deepEqual(readinessHints(readiness).map((hint) => [hint.key, hint.section]), [['sat', 'tests'], ['activities', 'activities']]);
  assert.deepEqual(readinessHints({ percent: 100, missing: [] }), []);
  assert.deepEqual(readinessHints(undefined), []);
});

test('country lists read with a space after each comma', () => {
  assert.equal(listText('Singapore,Hong Kong,USA'), 'Singapore, Hong Kong, USA');
  assert.equal(listText(['UK', 'Canada']), 'UK, Canada');
  assert.equal(listText(''), '');
  assert.equal(listText(null), '');
});
