import test from 'node:test';
import assert from 'node:assert/strict';
import { documentContentFields } from '../src/lib/documentFields.js';

const link = 'https://docs.google.com/document/d/abc/edit';
const linkDoc = { id: 3, google_docs_url: link, has_file: false };

test('an unchanged link is not re-sent, so renaming keeps the review status', () => {
  assert.deepEqual(documentContentFields({ doc: linkDoc, source: 'link', link }), {});
  assert.deepEqual(documentContentFields({ doc: linkDoc, source: 'link', link: `${link}?x` }), { google_docs_url: `${link}?x` });
});

test('a new document always sends its link; switching from a file drops the file', () => {
  assert.deepEqual(documentContentFields({ source: 'link', link }), { google_docs_url: link });
  assert.deepEqual(documentContentFields({ doc: { id: 4, google_docs_url: '', has_file: true }, source: 'link', link }), { google_docs_url: link, file: null });
});

test('a new file replaces a stored link; keeping the file sends nothing', () => {
  const file = { name: 'cv.pdf' };
  assert.deepEqual(documentContentFields({ doc: linkDoc, source: 'file', file }), { file, google_docs_url: '' });
  assert.deepEqual(documentContentFields({ doc: { id: 5, has_file: true }, source: 'file' }), {});
});
