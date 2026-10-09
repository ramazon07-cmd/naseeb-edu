import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage, TRANSLATIONS } = await import('../src/i18n.js');
const { STUDENT_AUTHORED_RECORDS, canDeleteStudentRecord, changedPayload, editableFields, recordErrorMessage } = await import('../src/lib/studentAuthored.js');

const ESSAY_FIELDS = [['application'], ['title'], ['prompt'], ['content'], ['status'], ['google_docs_url'], ['counselor_comment']];
const CODES = ['essay_changed', 'precondition_required', 'student_authored', 'student_authored_delete'];

test('staff get no delete action on student-authored records; the student keeps it', () => {
  for (const resource of STUDENT_AUTHORED_RECORDS) {
    for (const role of ['counselor', 'admin', 'teacher', 'organization', 'parent']) assert.equal(canDeleteStudentRecord({ role }, resource), false, `${role} ${resource}`);
    assert.equal(canDeleteStudentRecord({ role: 'student' }, resource), true);
  }
  assert.equal(canDeleteStudentRecord({ role: 'counselor' }, 'applications'), true);
});

test('staff edit only the review fields of student work', () => {
  assert.deepEqual(editableFields({ role: 'counselor' }, 'essays', ESSAY_FIELDS).map(([name]) => name), ['status', 'counselor_comment']);
  assert.deepEqual(editableFields({ role: 'counselor' }, 'achievements', [['title'], ['description']]), []);
  assert.equal(editableFields({ role: 'student' }, 'essays', ESSAY_FIELDS), ESSAY_FIELDS);
  assert.deepEqual(editableFields({ role: 'counselor' }, 'applications', [['notes']]), [['notes']]);
});

test('an edit sends only the fields that changed', () => {
  const item = { title: 'Bread', content: 'Old', status: 'draft', application: null, verified: true, counselor_comment: '' };
  assert.deepEqual(changedPayload({ title: 'Bread', content: 'Old', status: 'reviewing', application: null, verified: true, counselor_comment: 'Nice' }, item), { status: 'reviewing', counselor_comment: 'Nice' });
  assert.deepEqual(changedPayload({ application: '' }, { application: null }), {});
  assert.deepEqual(changedPayload({ application: '4' }, { application: 4 }), {});
});

test('each server error code has a translated message', () => {
  setLanguage('en');
  for (const code of CODES) {
    const message = recordErrorMessage({ details: { code }, message: 'raw' });
    assert.notEqual(message, 'raw', code);
    for (const language of ['uz', 'ru']) assert.ok(TRANSLATIONS[language][message], `${language}: ${code}`);
  }
  assert.equal(recordErrorMessage({ details: { code: 'other' }, message: 'Bad title' }), 'Bad title');
});

test('only stale-copy codes trigger a reload', async () => {
  const { isStaleCopyError } = await import('../src/lib/studentAuthored.js');
  assert.equal(isStaleCopyError({ details: { code: 'essay_changed' } }), true);
  assert.equal(isStaleCopyError({ details: { code: 'precondition_required' } }), true);
  assert.equal(isStaleCopyError({ details: { code: 'student_authored' } }), false);
});

test('the record form uses these rules', () => {
  const source = readFileSync(new URL('../src/pages/ResourceSection.jsx', import.meta.url), 'utf8');
  assert.match(source, /if \(base\) payload = changedPayload\(payload, base\)/);
  // Each changed essay field carries the value it was loaded with; a conflict reloads the copy, keeping what was typed.
  assert.match(source, /payload\.original = Object\.fromEntries\(Object\.keys\(payload\)\.map\(\(name\) => \[name, base\[name\] \?\? null\]\)\)/);
  assert.match(source, /isStaleCopyError\(err\)\) api\.retrieve\(resource, item\.id\)\.then\(setBase/);
  // A status the user can't choose is shown read-only and left out of the payload.
  assert.match(source, /value && !choices\.includes\(value\)\) return <Field label=\{t\(labelText\)\}><input value=\{label\(value\)\} readOnly disabled \/>/);
  assert.match(source, /if \(type !== 'checkbox' && !values\.has\(name\)\) continue;/);
  assert.match(source, /item \? editableFields\(user, resource, allFields\) : allFields/);
  assert.match(source, /allowCreate && canDeleteStudentRecord\(user, resource\)/);
  assert.match(source, /notify\(recordErrorMessage\(err\), 'error'\)/);
});
