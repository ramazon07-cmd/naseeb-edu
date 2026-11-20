import test from 'node:test';
import assert from 'node:assert/strict';
import {
  applyNoteState, deltaSince, doneNotes, goneNotes, headline, levelWord, normalizeCheck, normalizeForFingerprint, openNotes, recheckBlock, serverNotice,
  textFingerprint,
} from '../src/essayLab/coachModel.js';

test('fingerprint normalization matches the server rules', async () => {
  assert.equal(normalizeForFingerprint('I don’t know, “really”.'), 'i dont know really');
  assert.equal(normalizeForFingerprint('  Hello,\n\n  World!!  '), 'hello world');
  const base = await textFingerprint('Hello, World');
  // Same digests as the server's Python implementation (sha256 of the normalized text).
  assert.equal(base, 'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9');
  assert.equal(await textFingerprint('I don’t know, “really”.'), '0ccb1a9b61b7cb72e63fa8f7783eb39201400a21555bbad02b302f96f7ea5772');
  assert.equal(await textFingerprint('hello world'), base, 'case and punctuation do not matter');
  assert.equal(await textFingerprint('Hello — World...'), base, 'punctuation-only edits give the same fingerprint');
  assert.equal(await textFingerprint('Hello,   World'), base, 'whitespace does not matter');
  assert.notEqual(await textFingerprint('Hello, Worlds'), base, 'a word change differs');
  assert.equal(await textFingerprint('I don’t know'), await textFingerprint('I don\'t know'), 'curly and straight quotes match');
});

test('headline and level words follow the contract', () => {
  assert.equal(headline(0), 'Early depth');
  assert.equal(headline(50), 'Early depth');
  assert.equal(headline(51), 'Developing depth');
  assert.equal(headline(70), 'Developing depth');
  assert.equal(headline(71), 'Solid depth');
  assert.equal(headline(80), 'Solid depth');
  assert.equal(headline(81), 'Strong depth');
  assert.equal(headline(100), 'Strong depth');
  assert.equal(headline(null), null);
  assert.deepEqual([1, 2, 3, 4].map(levelWord), ['Emerging', 'Developing', 'Solid', 'Strong']);
  assert.equal(levelWord(0), null);
  assert.equal(deltaSince(76, 66), 10);
  assert.equal(deltaSince(60, 66), null, 'only improvements are shown');
  assert.equal(deltaSince(60, null), null);
});

test('re-check button state: open notes, unchanged text, ready', () => {
  assert.equal(recheckBlock({ hasCheck: false, openCount: 0, changed: false }), null, 'the first check is always allowed');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 2, changed: true }), 'notes_open');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 2, changed: false }), 'notes_open', 'notes come first');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 0, changed: false }), 'unchanged');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 0, changed: true }), null);
  assert.equal(serverNotice({ details: { code: 'notes_open' } }), 'notes_open');
  assert.equal(serverNotice({ details: { code: 'too_small_change' } }), 'too_small_change');
  assert.equal(serverNotice({ details: { code: 'slow_down' } }), null);
});

test('old checks are mapped to the new shape', () => {
  const model = normalizeCheck({
    result: {
      scores: { reflection: 2, specificity: 2, voice: 3, structure: 3, prompt_fit: 3 },
      summary: 'Old summary',
      strengths: ['Nice voice'],
      notes: [
        { id: 'a', kind: 'reflect', quote: 'q1', question: 'Why?', why: 'Because' },
        { id: 'b', kind: 'specific', quote: 'q2', question: 'Which one?' },
        { id: 'c', kind: 'clarity', quote: 'q3', question: 'Clearer?' },
        { id: 'd', kind: 'strength', quote: 'q4', question: 'Good line' },
      ],
    },
  });
  assert.equal(model.version2, false);
  assert.equal(model.scored, false, 'only version 2 is scored');
  assert.equal(model.overall, 65, 'overall falls back to the old scores');
  assert.deepEqual(model.notes.map((note) => note.criterion), ['reflection', 'specificity', 'structure']);
  assert.equal(model.notes[0].context, 'Because');
  assert.equal(model.notes.some((note) => note.priority), false);
  assert.deepEqual(model.strengths.map((item) => item.text), ['Good line', 'Nice voice']);
  assert.equal(model.strengths[0].quote, 'q4');
  assert.equal(normalizeCheck(null), null);
});

test('version 2 checks keep what the server says', () => {
  const model = normalizeCheck({
    result: {
      version: 2, scored: true, overall: 66, scores: { reflection: 2 }, summary: 's', suggestions: ['one', '', 'two'],
      strengths: [{ id: 's1', criterion: 'voice', quote: 'x', text: 'why' }], notes_locked: false,
      notes: [{ id: 'n1', criterion: 'prompt_fit', quote: 'q', question: 'Q?', context: '', priority: true }],
    },
  });
  assert.equal(model.scored, true);
  assert.equal(model.overall, 66);
  assert.deepEqual(model.suggestions, ['one', 'two']);
  assert.equal(model.notes[0].criterion, 'prompt_fit');
  assert.equal(model.notes[0].priority, true);
  assert.equal(model.strengths[0].quote, 'x');
  const unscored = normalizeCheck({ result: { version: 2, scored: false, overall: null, notes: [] } });
  assert.equal(unscored.scored, false);
  assert.equal(normalizeCheck({ result: { version: 2, scored: true, overall: 40, notes_locked: true, notes: [] } }).notesLocked, true);
});

test('note state reducer and open/done/gone lists', () => {
  let states = {};
  states = applyNoteState(states, 'n1', 'done');
  states = applyNoteState(states, 'n2', 'dismissed');
  assert.deepEqual(states, { n1: 'done', n2: 'dismissed' });
  const before = states;
  states = applyNoteState(states, 'n1', 'open');
  assert.deepEqual(states, { n2: 'dismissed' });
  assert.deepEqual(before, { n1: 'done', n2: 'dismissed' }, 'the old object is not changed');
  assert.deepEqual(applyNoteState(null, 'x', 'done'), { x: 'done' });

  const notes = [{ id: 'n1' }, { id: 'n2' }, { id: 'n3' }, { id: 'n4' }];
  const anchored = new Set(['n1', 'n2', 'n3']);
  const marked = { n1: 'done', n2: 'dismissed' };
  assert.deepEqual(openNotes(notes, marked, anchored).map((note) => note.id), ['n3'], 'n4 lost its sentence and counts as resolved');
  assert.deepEqual(doneNotes(notes, marked).map((note) => note.id), ['n1', 'n2']);
  assert.deepEqual(goneNotes(notes, marked, anchored).map((note) => note.id), ['n4']);
});

test('gone notes are resolved but not listed as done', () => {
  const notes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const states = applyNoteState({ a: 'done' }, 'b', 'gone');
  assert.deepEqual(states, { a: 'done', b: 'gone' });
  const anchored = new Set(['a', 'c']);
  assert.deepEqual(openNotes(notes, states, anchored).map((note) => note.id), ['c']);
  assert.deepEqual(doneNotes(notes, states).map((note) => note.id), ['a']);
  assert.deepEqual(goneNotes(notes, states, anchored).map((note) => note.id), ['b']);
});
