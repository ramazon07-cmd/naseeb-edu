import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage, TRANSLATIONS } = await import('../src/i18n.js');
const { ESSAY_CHANGED_MESSAGE, essaySaveError } = await import('../src/lib/essayConflict.js');

test('a stale essay save explains that the essay changed and needs a reload', () => {
  setLanguage('en');
  assert.equal(essaySaveError('essays', { status: 409, message: 'raw' }), ESSAY_CHANGED_MESSAGE);
  assert.match(essaySaveError('essays', { status: 409 }), /Reload/);
});

test('other errors keep the server message', () => {
  assert.equal(essaySaveError('essays', { status: 400, message: 'Bad title' }), 'Bad title');
  assert.equal(essaySaveError('tasks', { status: 409, message: 'Busy' }), 'Busy');
});

test('the message is translated', () => {
  for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][ESSAY_CHANGED_MESSAGE], language);
});

test('the essay edit form sends the copy it was built from', () => {
  const source = readFileSync(new URL('../src/pages/ResourceSection.jsx', import.meta.url), 'utf8');
  assert.match(source, /resource === 'essays'\) payload\.updated_at = item\.updated_at/);
  assert.match(source, /essaySaveError\(resource, err\)/);
});
