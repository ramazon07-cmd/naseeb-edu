// Deleting a student deactivates the account (data is kept), so the student
// table must not present it as a delete. Other record lists keep delete.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { TRANSLATIONS } = await import('../src/i18n.js');

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
const records = read('components/records.jsx');
const studentsPage = read('pages/StudentsPage.jsx');
const resources = read('pages/ResourceSection.jsx');
const studentTable = records.slice(records.indexOf('export function StudentTable'));

test('student rows offer deactivate, not delete', () => {
  assert.match(studentTable, /onDeactivate && <button className="icon-button danger" onClick=\{\(\) => onDeactivate\(student\)\} title=\{t\("Deactivate student"\)\} aria-label=\{t\("Deactivate student"\)\}><UserX size=\{16\} \/><\/button>/);
  assert.doesNotMatch(studentTable, /Trash2|onDelete|t\("Delete"\)/);
  assert.match(records, /import \{[^}]*\bUserX\b[^}]*\} from 'lucide-react'/);
  assert.doesNotMatch(records, /\bTrash2\b/);
});

test('the students page confirms that data is kept', () => {
  assert.match(studentsPage, /<StudentTable [^]*?onDeactivate=\{isPlatformAdmin\(user\) \? deactivate : undefined\}/);
  const confirm = studentsPage.match(/async function deactivate\(student\) \{\s*if \(!window\.confirm\(tx`([^`]*)`/)[1];
  assert.match(confirm, /Their data is kept\./);
  assert.doesNotMatch(studentsPage, /onDelete=/);
});

test('other resource lists keep delete', () => {
  assert.match(resources, /t\("Delete this record\?"\)/);
  assert.match(resources, /<Trash2 /);
});

test('new strings have Uzbek and Russian text', () => {
  for (const key of ['Deactivate student', 'Deactivate {0}? They can no longer sign in. Their data is kept.']) {
    for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][key], `${language}: ${key}`);
  }
  assert.match(TRANSLATIONS.ru['Deactivate student'], /Деактивировать/);
});
