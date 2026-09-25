import test from 'node:test';
import assert from 'node:assert/strict';
import { buildIndex, findQuote, locateQuotes, normalizeText } from '../src/essayLab/anchors.js';

test('normalizes like the backend: NFKC, straight quotes, collapsed whitespace', () => {
  assert.equal(normalizeText('“It stopped   singing,” he said’s ﬁne'), '"It stopped singing," he said\'s fine');
  assert.equal(normalizeText('a\n\tb'), 'a b');
});

test('finds a quote and maps it back to original offsets', () => {
  const text = 'He said only, “It stopped singing.”  Then he left.';
  const index = buildIndex(text);
  const hit = findQuote(index, '"It stopped singing."');
  assert.deepEqual(hit, {from: text.indexOf('“'), to: text.indexOf('”') + 1});
  assert.equal(text.slice(hit.from, hit.to), '“It stopped singing.”');
});

test('matches across collapsed whitespace and ligatures', () => {
  const text = 'The   ﬁrst radio  was broken';
  const hit = findQuote(buildIndex(text), 'first radio was');
  assert.equal(text.slice(hit.from, hit.to), 'ﬁrst radio  was');
  const lig = findQuote(buildIndex('a ﬁ b'), 'f');
  assert.deepEqual(lig, {from: 2, to: 3});
});

test('composes decomposed accents the way NFKC does', () => {
  const text = 'Café society';
  const hit = findQuote(buildIndex(text), 'Café');
  assert.deepEqual(hit, {from: 0, to: 5});
});

test('returns null for a missing or empty quote', () => {
  assert.equal(findQuote(buildIndex('hello world'), 'goodbye'), null);
  assert.equal(findQuote(buildIndex('hello world'), '   '), null);
  assert.equal(findQuote(buildIndex(''), 'x'), null);
});

test('drops a plain-text list prefix the editor does not show', () => {
  const hit = findQuote(buildIndex('apples and pears'), '• apples and');
  assert.deepEqual(hit, {from: 0, to: 10});
  assert.deepEqual(findQuote(buildIndex('first step'), '1. first'), {from: 0, to: 5});
});

test('with repeated text prefers the match nearest the hint', () => {
  const text = 'I listened. Later, I listened. Again I listened.';
  const index = buildIndex(text);
  assert.equal(findQuote(index, 'I listened').from, 0);
  assert.equal(findQuote(index, 'I listened', 22).from, text.indexOf('I listened', 5));
  assert.equal(findQuote(index, 'I listened', 100).from, text.lastIndexOf('I listened'));
});

test('locateQuotes searches block by block, drops missing quotes and re-anchors', () => {
  const blocks = [
    {offset: 1, index: buildIndex('The radio arrived wrapped in cloth.')},
    {offset: 40, index: buildIndex('It was a small problem with a wire.')},
    {offset: 80, index: buildIndex('It was a small problem again.')},
  ];
  const notes = [
    {id: 'n1', quote: 'It was a small problem'},
    {id: 'n2', quote: 'wrapped in cloth'},
    {id: 'n3', quote: 'no longer here'},
    {id: 'n4', quote: 'arrived wrapped in cloth. It was'}, // spans paragraphs -> never found
  ];
  const located = locateQuotes(blocks, notes);
  assert.deepEqual(located.get('n1'), {from: 40, to: 62});
  assert.deepEqual(located.get('n2'), {from: 1 + 18, to: 1 + 34});
  assert.equal(located.has('n3'), false);
  assert.equal(located.has('n4'), false);
  const moved = locateQuotes(blocks, notes, new Map([['n1', 81]]));
  assert.deepEqual(moved.get('n1'), {from: 80, to: 102});
});
