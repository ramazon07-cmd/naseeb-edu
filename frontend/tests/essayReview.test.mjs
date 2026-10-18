import test from 'node:test';
import assert from 'node:assert/strict';
import { accessLevel, blockLength, leafSpans, safeHref, splitThreads, textBetween } from '../src/lib/essayReview.js';

const text = (value, marks) => ({ type: 'text', text: value, ...(marks ? { marks } : {}) });
const paragraph = (...content) => ({ type: 'paragraph', content });
const list = { type: 'bulletList', attrs: { bid: 'l1' }, content: [
  { type: 'listItem', content: [paragraph(text('one'))] },
  { type: 'listItem', content: [paragraph(text('two'), { type: 'hardBreak' }, text('x'))] },
] };

test('text blocks inside one block are one unit apart and a line break is one unit', () => {
  const spans = leafSpans(list).map(({ start, end }) => [start, end]);
  assert.deepEqual(spans, [[0, 3], [4, 9]]);
  assert.equal(blockLength(list), 9);
  assert.equal(blockLength({ type: 'pageBreak' }), 0);
});

test('offsets count UTF-16 units like the server', () => {
  const block = paragraph(text('a😀b'));
  assert.equal(blockLength(block), 4);
  assert.equal(textBetween(block, 3, 4), 'b');
});

test('the words between two offsets', () => {
  const block = paragraph(text('Hello '), text('big', [{ type: 'bold' }]), text(' world'));
  assert.equal(textBetween(block, 6, 9), 'big');
  assert.equal(textBetween(block, 0, 5), 'Hello');
  assert.equal(textBetween(list, 2, 6), 'e tw');
});

test('what a reader may do follows the owner\'s choice', () => {
  assert.equal(accessLevel(['view', 'comment', 'suggest', 'edit']), 'suggest');
  assert.equal(accessLevel(['view', 'comment']), 'comment');
  assert.equal(accessLevel(['view']), 'view');
  assert.equal(accessLevel(), 'view');
});

test('open threads come before resolved ones, oldest first', () => {
  const { open, resolved } = splitThreads([
    { id: 2, status: 'open', created_at: '2026-10-02' },
    { id: 3, status: 'resolved', created_at: '2026-10-01' },
    { id: 1, status: 'open', created_at: '2026-10-01' },
  ]);
  assert.deepEqual(open.map((thread) => thread.id), [1, 2]);
  assert.deepEqual(resolved.map((thread) => thread.id), [3]);
});

test('only web and mail links are followed', () => {
  assert.equal(safeHref('https://example.com/a'), 'https://example.com/a');
  assert.equal(safeHref('mailto:a@b.co'), 'mailto:a@b.co');
  assert.equal(safeHref('javascript:alert(1)'), '');
  assert.equal(safeHref(''), '');
});
