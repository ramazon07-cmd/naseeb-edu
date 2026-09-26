import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { countWords, deriveText, docFromText, docToText, docWordCount, makePreview, validateDoc } from '../src/essayLab/docText.js';

// Copied from backend/apps/admissions/essay_lab/fixtures/doc_text_cases.json (shared with the backend tests).
const {cases} = JSON.parse(readFileSync(new URL('./fixtures/doc_text_cases.json', import.meta.url), 'utf8'));

for (const fixture of cases) {
  test(`backend fixture: ${fixture.name}`, () => {
    const derived = deriveText(fixture.doc);
    assert.equal(derived.content, fixture.content);
    assert.equal(derived.wordCount, fixture.word_count);
    assert.equal(derived.preview, fixture.preview);
    assert.equal(derived.charCount, fixture.char_count);
    assert.equal(derived.charCountNoSpaces, fixture.char_count_no_spaces);
    assert.equal(docToText(fixture.doc), fixture.content);
    assert.equal(docWordCount(fixture.doc), fixture.word_count);
    assert.equal(validateDoc(fixture.doc), null);
  });
}

test('list markers go on the first block of an item even when it is empty, and never count as words', () => {
  const doc = {type: 'doc', content: [
    {type: 'bulletList', attrs: {style: 'dash'}, content: [
      {type: 'listItem', content: [{type: 'paragraph'}, {type: 'paragraph', content: [{type: 'text', text: 'second block'}]}]},
      {type: 'listItem', content: [{type: 'paragraph', content: [{type: 'text', text: '  '}]}]},
      {type: 'listItem', content: [{type: 'paragraph', content: [{type: 'text', text: 'third'}]}]},
    ]},
    {type: 'paragraph', content: [{type: 'text', text: 'Toshkent\u00a0— “bozor”  va\u0007 ‘non’'}]},
  ]};
  assert.deepEqual(deriveText(doc), {
    content: 'second block\n\n– third\n\nToshkent\u00a0— “bozor”  va ‘non’',
    wordCount: 8,
    preview: 'second block – third Toshkent — “bozor” va ‘non’',
    charCount: 12 + 5 + 28,
    charCountNoSpaces: 11 + 5 + 23,
  });
});

test('preview cuts at a word boundary like the backend', () => {
  const words = Array.from({length: 60}, (_, i) => `word${i}`).join(' ');
  const preview = makePreview(words);
  assert.ok(preview.endsWith('…'));
  assert.ok([...preview].length <= 161);
  assert.ok(!preview.slice(0, -1).endsWith(' '));
  assert.equal(makePreview('  short \n\n text  '), 'short text');
});

test('counts \\S+ runs as words', () => {
  assert.equal(countWords(''), 0);
  assert.equal(countWords('  one\ttwo\n\nthree  '), 3);
  assert.equal(countWords("don't — stop"), 3);
  assert.equal(countWords('a\ufeffb'), 1, 'U+FEFF is not whitespace in Python either');
  assert.equal(countWords('a\u0085b\u2003c'), 3);
  assert.equal(docToText(null), '');
});

test('docFromText splits blank lines into paragraphs and keeps single newlines as hard breaks', () => {
  const doc = docFromText('\nFirst para\nsame para\n\n\nSecond para\r\n\r\nThird\n\n   \n');
  assert.deepEqual(doc, {type: 'doc', content: [
    {type: 'paragraph', content: [{type: 'text', text: 'First para'}, {type: 'hardBreak'}, {type: 'text', text: 'same para'}]},
    {type: 'paragraph', content: [{type: 'text', text: 'Second para'}]},
    {type: 'paragraph', content: [{type: 'text', text: 'Third'}]},
  ]});
  assert.equal(docToText(doc), 'First para\nsame para\n\nSecond para\n\nThird');
  assert.deepEqual(docFromText(''), {type: 'doc', content: [{type: 'paragraph'}]});
});

test('text survives a docFromText round trip', () => {
  for (const fixture of cases) {
    if (!fixture.content) continue;
    assert.equal(docToText(docFromText(fixture.content)), fixture.content);
  }
});

test('validateDoc mirrors the backend limits', () => {
  assert.equal(validateDoc({type: 'doc', content: [{type: 'codeBlock'}]}), 'invalid_doc');
  assert.equal(validateDoc({type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: 'x', marks: [{type: 'code'}]}]}]}), 'invalid_doc');
  assert.equal(validateDoc({type: 'paragraph'}), 'invalid_doc');
  let deep = {type: 'paragraph'};
  for (let i = 0; i < 14; i += 1) deep = {type: 'blockquote', content: [deep]};
  assert.equal(validateDoc({type: 'doc', content: [deep]}), 'invalid_doc');
  const big = {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: 'x'.repeat(270 * 1024)}]}]};
  assert.equal(validateDoc(big), 'doc_too_large');
});
