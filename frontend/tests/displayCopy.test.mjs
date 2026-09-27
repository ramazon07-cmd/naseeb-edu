import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS, setLanguage, tp } = await import('../src/i18n.js');
const { AUDIT_ACTIONS, LABELS, auditActionLabel, label } = await import('../src/lib/labels.js');
const { gradeText, joinParts, programUsageCaption, testScoreCaption } = await import('../src/lib/format.js');

test('document types read as proper names, not raw codes', () => {
  setLanguage('en');
  assert.equal(label('certificate'), 'Certificate');
  assert.equal(label('cv'), 'CV / Résumé');
  assert.equal(label('ielts'), 'IELTS');
  assert.equal(label('recommendation'), 'Recommendation letter');
  assert.equal(label('changes_requested'), 'Changes requested');
});

test('every enum label and audit action has Uzbek and Russian text', () => {
  const missing = [...Object.values(LABELS), ...Object.values(AUDIT_ACTIONS)]
    .flatMap((text) => ['uz', 'ru'].filter((language) => !TRANSLATIONS[language][text]).map((language) => `${language}: ${text}`));
  assert.deepEqual(missing, []);
});

test('audit actions are sentences; unknown codes fall back to words', () => {
  setLanguage('en');
  assert.equal(auditActionLabel('school.created'), 'School created');
  assert.equal(auditActionLabel('student_360'), 'Student 360');
  assert.equal(auditActionLabel('new_thing.done'), 'New thing done');
});

test('joinParts never leaves a dangling or doubled separator', () => {
  assert.equal(joinParts('Anna', '', null, '—', 'High'), 'Anna · High');
  assert.equal(joinParts(undefined, 'Only'), 'Only');
  assert.equal(joinParts('', '—', false), '');
  assert.equal(joinParts(['A', ['B']], 0), 'A · B · 0');
});

test('usage and score captions leave out zero counts instead of printing 0', () => {
  setLanguage('en');
  const hours = (value) => `${value} h`;
  assert.equal(programUsageCaption({ total: 10, used: 5, unlimited: 0, hours }), '5 h used of 10 h');
  assert.equal(programUsageCaption({ total: 0, used: 0, unlimited: 2, hours }), '2 unlimited services');
  assert.equal(programUsageCaption({ total: 4, used: 0, unlimited: 1, hours }), '0 h used of 4 h · 1 unlimited service');
  assert.equal(testScoreCaption({ ielts_score: 0, sat_score: 1400 }), 'SAT 1400');
  assert.equal(testScoreCaption({ ielts_score: '7.5', sat_score: 0 }), 'IELTS 7.5');
  assert.equal(testScoreCaption({ ielts_score: null, sat_score: null }), '');
});

test('gradeText names gap years and hides a missing grade', () => {
  setLanguage('en');
  assert.equal(gradeText('10'), 'Grade 10');
  assert.equal(gradeText('gap'), 'Gap year');
  assert.equal(gradeText(''), '');
  assert.equal(gradeText(null), '');
});

test('English plural keys pick the singular form for one', () => {
  setLanguage('en');
  assert.equal(tp('{n} student|{n} students', 1, { n: 1 }), '1 student');
  assert.equal(tp('{n} student|{n} students', 3, { n: 3 }), '3 students');
  setLanguage('ru');
  assert.equal(tp('{n} student|{n} students', 3, { n: 3 }), '3 ученика');
  assert.equal(tp('{n} student|{n} students', 5, { n: 5 }), '5 учеников');
  setLanguage('en');
});

test('task progress reads as a sentence with the right plural', () => {
  const key = '{done} of {n} task done|{done} of {n} tasks done';
  setLanguage('en');
  assert.equal(tp(key, 4, { done: 0, n: 4 }), '0 of 4 tasks done');
  assert.equal(tp(key, 1, { done: 1, n: 1 }), '1 of 1 task done');
  setLanguage('ru');
  assert.equal(tp(key, 1, { done: 0, n: 1 }), 'Выполнено 0 из 1 задания');
  assert.equal(tp(key, 5, { done: 2, n: 5 }), 'Выполнено 2 из 5 заданий');
  setLanguage('en');
});
