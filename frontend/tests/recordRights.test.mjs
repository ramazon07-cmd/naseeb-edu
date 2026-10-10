import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} }, navigator: { language: 'en' }, location: { search: '' } };
const { setLanguage } = await import('../src/i18n.js');
const { ERROR_CODE_TRANSLATIONS } = await import('../src/translations/errorCodes.js');
const { canDelete, changedPayload, editableFields, isStaleCopyError, recordErrorMessage } = await import('../src/lib/recordRights.js');

const ESSAY_FIELDS = [['application'], ['title'], ['prompt'], ['content'], ['status'], ['google_docs_url'], ['counselor_comment']];

test('the form shows only the fields the API says this user may change', () => {
  const review = { editable_fields: ['status', 'counselor_comment'] };
  assert.deepEqual(editableFields(review, ESSAY_FIELDS).map(([name]) => name), ['status', 'counselor_comment']);
  assert.deepEqual(editableFields({ editable_fields: [] }, ESSAY_FIELDS), []);
  // Records the API does not annotate keep every field.
  assert.equal(editableFields({ id: 1 }, ESSAY_FIELDS), ESSAY_FIELDS);
});

test('delete follows can_delete, falling back for unannotated records', () => {
  assert.equal(canDelete({ can_delete: false }, true), false);
  assert.equal(canDelete({ can_delete: true }, false), true);
  assert.equal(canDelete({ id: 1 }, true), true);
});

test('an edit sends only the fields that changed', () => {
  const item = { title: 'Bread', content: 'Old', status: 'draft', application: null, verified: true, counselor_comment: '' };
  assert.deepEqual(changedPayload({ title: 'Bread', content: 'Old', status: 'reviewing', application: null, verified: true, counselor_comment: 'Nice' }, item), { status: 'reviewing', counselor_comment: 'Nice' });
  assert.deepEqual(changedPayload({ application: '' }, { application: null }), {});
  assert.deepEqual(changedPayload({ application: '4' }, { application: 4 }), {});
});

test('only stale-copy codes trigger a reload', () => {
  assert.equal(isStaleCopyError({ details: { code: 'essay_changed' } }), true);
  assert.equal(isStaleCopyError({ details: { code: 'precondition_required' } }), true);
  assert.equal(isStaleCopyError({ details: { code: 'student_authored' } }), false);
});

test('error messages are keyed by code; English uses the server text', () => {
  const error = (code) => ({ details: { code, detail: 'Server sentence.' }, message: 'Server sentence.' });
  for (const code of Object.keys(ERROR_CODE_TRANSLATIONS)) {
    for (const [language, index] of [['uz', 0], ['ru', 1]]) {
      setLanguage(language);
      assert.equal(recordErrorMessage(error(code)), ERROR_CODE_TRANSLATIONS[code][index], `${language}: ${code}`);
    }
    setLanguage('en');
    assert.equal(recordErrorMessage(error(code)), 'Server sentence.');
  }
  setLanguage('uz');
  assert.equal(recordErrorMessage(error('unknown_code')), 'Server sentence.');
  setLanguage('en');
});

test('the record form uses these rules', () => {
  const source = readFileSync(new URL('../src/pages/ResourceSection.jsx', import.meta.url), 'utf8');
  assert.match(source, /const itemEditable = allowEdit && !counselorLetter && editableFields\(item, RESOURCE_FIELDS\[resource\] \|\| \[\]\)\.length > 0;/);
  assert.match(source, /allowCreate && canDelete\(item, true\)/);
  // A letter the counselor wrote stays read-only for the student whatever the record allows.
  assert.match(source, /const allowDelete = !counselorLetter && \(/);
  assert.match(source, /item \? editableFields\(item, allFields\) : allFields/);
  assert.match(source, /if \(base\) payload = changedPayload\(payload, base\)/);
  // Each changed essay field carries the value it was loaded with; a conflict reloads the copy, keeping what was typed.
  assert.match(source, /payload\.original = Object\.fromEntries\(Object\.keys\(payload\)\.map\(\(name\) => \[name, base\[name\] \?\? null\]\)\)/);
  assert.match(source, /isStaleCopyError\(err\)\) api\.retrieve\(resource, item\.id\)\.then\(setBase/);
  // A status the user can't choose is shown read-only and left out of the payload.
  assert.match(source, /value && !choices\.includes\(value\)\) return <Field label=\{t\(labelText\)\}><input value=\{label\(value\)\} readOnly disabled \/>/);
  assert.match(source, /if \(type !== 'checkbox' && !values\.has\(name\)\) continue;/);
  assert.match(source, /notify\(recordErrorMessage\(err\), 'error'\)/);
});
