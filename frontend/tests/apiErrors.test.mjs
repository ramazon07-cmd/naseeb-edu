import test from 'node:test';
import assert from 'node:assert/strict';
import { errorPayloadMessage, formatValidationErrors, humanizeField } from '../src/lib/apiErrors.js';

test('field names become readable labels', () => {
  assert.equal(humanizeField('target_countries'), 'Target countries');
  assert.equal(humanizeField('sat_math'), 'Sat math');
  assert.equal(humanizeField('0'), '#1');
});

test('general errors have no field prefix; nested errors keep their path', () => {
  assert.equal(formatValidationErrors({ non_field_errors: ['Passwords do not match.'] }), 'Passwords do not match.');
  assert.equal(
    formatValidationErrors({ email: ['Enter a valid email address.'], missions: [{}, { title: ['This field is required.'] }] }),
    'Email: Enter a valid email address. • Missions › #2 › Title: This field is required.',
  );
});

test('labels go through the translator', () => {
  const uz = { 'Email': 'Elektron pochta' };
  assert.equal(formatValidationErrors({ email: ['Noto‘g‘ri.'] }, (text) => uz[text] || text), 'Elektron pochta: Noto‘g‘ri.');
});

test('field errors are listed instead of the top-level detail', () => {
  assert.equal(
    errorPayloadMessage({ detail: 'Invalid input.', code: 'invalid', errors: { email: ['Enter a valid email address.'], sat_math: ['Must be 200–800.'] } }),
    'Email: Enter a valid email address. • Sat math: Must be 200–800.',
  );
  assert.equal(
    errorPayloadMessage({ detail: 'Invalid input.', username: ['This field is required.'], non_field_errors: ['Passwords do not match.'] }),
    'Username: This field is required. • Passwords do not match.',
  );
});

test('without field errors the detail is shown; metadata is never listed', () => {
  assert.equal(errorPayloadMessage({ detail: 'Not found.' }), 'Not found.');
  assert.equal(errorPayloadMessage({ detail: 'Essay changed elsewhere.', code: 'conflict', save_seq: 5, doc: { type: 'doc', content: [{ type: 'paragraph' }] } }), 'Essay changed elsewhere.');
  assert.equal(errorPayloadMessage({ email: ['Taken.'] }, (text) => ({ Email: 'Pochta' }[text] || text)), 'Pochta: Taken.');
  assert.equal(errorPayloadMessage(null), '');
});

test('student form fields in a server error are named in the reader language', async () => {
  globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
  const { setLanguage, t } = await import('../src/i18n.js');
  setLanguage('ru');
  const payload = { detail: 'Это поле обязательно.', starts_at: ['Это поле обязательно.'], duration_minutes: ['Введите целое число.'] };
  assert.equal(errorPayloadMessage(payload, t), 'Время начала: Это поле обязательно. • Длительность (мин): Введите целое число.');
  setLanguage('en');
});
