import test from 'node:test';
import assert from 'node:assert/strict';
import { collectSharedItems } from '../src/chatSharedItems.js';

const at = (id, extra = {}) => ({ id, body: '', created_at: '2026-09-25T12:00:00Z', ...extra });

test('uploaded photos go to Media and documents to Files, next to pasted links', () => {
  const items = collectSharedItems([
    at(1, { attachment_file: { name: 'scan.png', size: 10, is_image: true } }),
    at(2, { body: 'see https://example.com/guide.pdf', attachment_file: { name: 'cv.docx', size: 20, is_image: false } }),
    at(3, { body: 'https://example.com/page' }),
  ]);
  assert.deepEqual(items.map((item) => [item.kind, item.name, Boolean(item.attachment)]), [
    ['media', 'scan.png', true],
    ['files', 'cv.docx', true],
    ['files', 'guide.pdf', false],
    ['links', 'page', false],
  ]);
  assert.equal(new Set(items.map((item) => item.key)).size, items.length);
});

test('deleted messages contribute no files', () => {
  assert.deepEqual(collectSharedItems([at(1, { deleted_at: '2026-09-25T13:00:00Z', attachment_file: { name: 'a.pdf' } })]), []);
});
