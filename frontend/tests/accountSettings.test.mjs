import test from 'node:test';
import assert from 'node:assert/strict';
import { ACCOUNT_ERROR_MESSAGES, accountFieldErrors } from '../src/lib/accountSettings.js';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS } = await import('../src/i18n.js');

test('field errors map to their inputs and known messages are translated', () => {
  const translate = (text) => `T:${text}`;
  assert.deepEqual(
    accountFieldErrors({ current_password: ['Your current password is incorrect.'], new_password: ['This password is too common.', 'This password is entirely numeric.'] }, 'fallback', translate),
    { current_password: 'T:Your current password is incorrect.', new_password: 'This password is too common. This password is entirely numeric.' },
  );
  assert.deepEqual(accountFieldErrors({ email: ['This email address is already used by another account.'] }, '', translate), { email: 'T:This email address is already used by another account.' });
});

test('general errors and rate limits become a form message', () => {
  assert.deepEqual(accountFieldErrors({ detail: 'Request was throttled.' }, 'x'), { form: 'Request was throttled.' });
  assert.deepEqual(accountFieldErrors(null, 'Unable to connect.'), { form: 'Unable to connect.' });
  assert.deepEqual(accountFieldErrors({ code: 'x' }, 'Failed'), { form: 'Failed' });
  assert.deepEqual(accountFieldErrors([], ''), {});
});

test('every server message the page translates has Uzbek and Russian text', () => {
  for (const message of ACCOUNT_ERROR_MESSAGES) {
    for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][message], `${language}: ${message}`);
  }
});
