import test from 'node:test';
import assert from 'node:assert/strict';
import { applyNoteState, doneNotes, goneNotes, noteStateUpdates, openNotes, recheckBlock } from '../src/essayLab/coachModel.js';
import { buildPath, parsePath, resolveRoute } from '../src/lib/routes.js';
import { createIdeasController } from '../src/letters/ideasController.js';
import {
  LETTER_KEYS, aiIdeasOf, conflictError, fillCheckText, normalizeNewlines, sentenceAround, factLine, factsOf, fillStudent, insertAtCaret, locateNotes, mirrorSegments, noteAt, normalizeLetterCheck, wordCount,
} from '../src/letters/letterModel.js';

const LETTER = 'I have known Ramazon for two years.\n\nHe is a hardworking student. He leads the robotics club.\n\nHe is a hardworking student.';

// --- mirror highlight ranges ---------------------------------------------------------
test('a note is placed on its sentence, across a line break too', () => {
  const located = locateNotes(LETTER, [{ id: 'a', quote: 'He leads the robotics club.' }, { id: 'b', quote: 'He is a brilliant student.' }]);
  const a = located.get('a');
  assert.equal(LETTER.slice(a.from, a.to), 'He leads the robotics club.');
  assert.equal(located.has('b'), false, 'a quote that is not in the text is dropped');
  const across = locateNotes('First line.\nSecond   line.', [{ id: 'c', quote: 'First line. Second line.' }]).get('c');
  assert.deepEqual(across, { from: 0, to: 26 });
});

test('repeated sentences: notes with the same quote take different occurrences, hints keep their place', () => {
  const notes = [{ id: 'one', quote: 'He is a hardworking student.' }, { id: 'two', quote: 'He is a hardworking student.' }];
  const located = locateNotes(LETTER, notes);
  assert.notEqual(located.get('one').from, located.get('two').from);
  assert.ok(located.get('one').from < located.get('two').from);
  // A single note follows its hint to the second occurrence instead of jumping to the first.
  const second = located.get('two').from;
  const hinted = locateNotes(LETTER, [notes[1]], new Map([['two', second]]));
  assert.equal(hinted.get('two').from, second);
  // Text typed before it shifts both; the hint (old position) still picks the nearest copy.
  const edited = `Dear committee,\n\n${LETTER}`;
  const moved = locateNotes(edited, [notes[1]], new Map([['two', second]]));
  assert.equal(moved.get('two').from, second + 'Dear committee,\n\n'.length);
});

test('editing a sentence drops its note, restoring it brings it back', () => {
  const note = [{ id: 'x', quote: 'He leads the robotics club.' }];
  assert.equal(locateNotes(LETTER.replace('leads', 'joined'), note).has('x'), false);
  assert.equal(locateNotes(LETTER, note).has('x'), true);
});

test('mirror segments cover the whole text and split at every highlight edge', () => {
  const text = 'abcdefghij';
  const marks = [{ id: 'a', from: 2, to: 6, criterion: 'evidence' }, { id: 'b', from: 4, to: 8, criterion: 'voice' }];
  const segments = mirrorSegments(text, marks, 'b');
  assert.equal(segments.map((segment) => segment.text).join(''), text);
  assert.deepEqual(segments.map((segment) => [segment.from, segment.to, segment.ids]), [[0, 2, []], [2, 4, ['a']], [4, 6, ['a', 'b']], [6, 8, ['b']], [8, 10, []]]);
  assert.equal(segments[2].criterion, 'voice', 'the active note colours an overlap');
  assert.equal(segments[2].active, true);
  assert.equal(segments[0].criterion, null);
});

test('mirror segments ignore empty or out-of-range marks and clip to the text', () => {
  const segments = mirrorSegments('abc', [{ id: 'z', from: 2, to: 2, criterion: 'voice' }, { id: 'y', from: 5, to: 9, criterion: 'voice' }, { id: 'w', from: 1, to: 99, criterion: 'insight' }]);
  assert.deepEqual(segments.map((segment) => [segment.text, segment.ids]), [['a', []], ['bc', ['w']]]);
  assert.deepEqual(mirrorSegments('', []), []);
});

test('the caret finds the note under it', () => {
  const located = new Map([['a', { from: 0, to: 10 }], ['b', { from: 5, to: 20 }]]);
  assert.equal(noteAt(located, 2), 'a');
  assert.equal(noteAt(located, 7, 'b'), 'b');
  assert.equal(noteAt(located, 30), null);
});

// --- inserting from Ideas ---------------------------------------------------------------
test('insert goes at the caret with sensible spacing and keeps the caret after it', () => {
  assert.deepEqual(insertAtCaret('Hello world', 5, 5, 'dear'), { body: 'Hello dear world', caret: 10 });
  assert.deepEqual(insertAtCaret('', 0, 0, 'First.'), { body: 'First.', caret: 6 });
  assert.deepEqual(insertAtCaret('A.\n', 3, 3, 'B.'), { body: 'A.\nB.', caret: 5 });
  assert.equal(insertAtCaret('abc', 0, 0, 'toolong', 5), null);
});

test('[Student] is filled with the first name and a fact becomes one neutral line', () => {
  assert.equal(fillStudent('As lead, [Student] built it. [Student] won.', 'Ramazon'), 'As lead, Ramazon built it. Ramazon won.');
  assert.equal(factLine({ title: 'Robotics club', detail: 'Leader · 6 hours a week' }), 'Robotics club: Leader · 6 hours a week.');
  assert.equal(factLine({ title: 'GPA 4.9.', detail: '' }), 'GPA 4.9.');
  assert.equal(factLine({}), '');
  assert.equal(wordCount(' a  b\nc '), 3);
  const items = [{ kind: 'fact' }, { kind: 'sentence', text: 'x' }, { kind: 'idea', text: 'y' }, { kind: 'idea' }, { kind: 'tip' }];
  assert.equal(factsOf(items).length, 1);
  assert.equal(aiIdeasOf(items).length, 2);
});

// --- Ideas: facts are free and automatic, AI is a click -------------------------------------
function harness(responses = {}) {
  const calls = [];
  const timers = [];
  const controller = createIdeasController({
    load: async (payload) => { calls.push(payload); return typeof responses === 'function' ? responses(payload) : (payload.ai ? responses.ai : responses.facts) || { suggestions: [] }; },
    schedule: (fn, ms) => { const timer = { fn, ms, live: true }; timers.push(timer); return timer; },
    cancel: (timer) => { if (timer) timer.live = false; },
    debounceMs: 1500,
  });
  const fire = async () => { for (const timer of timers.splice(0)) if (timer.live) await timer.fn(); };
  return { controller, calls, timers, fire };
}
const ctx = (draft) => ({ draft, recommender_title: 'Counselor', relationship: 'Since grade 9' });

test('typing re-reads the profile facts once after a pause, never with ai:true', async () => {
  const { controller, calls, timers, fire } = harness({ facts: { suggestions: [{ kind: 'fact', source: 'honor', title: 'Olympiad', detail: '' }], ai_left: 17 } });
  await controller.start(ctx(''));
  assert.deepEqual(calls.map((call) => call.ai), [false]);
  controller.update(ctx('H'));
  controller.update(ctx('He'));
  controller.update(ctx('Hel'));
  assert.equal(timers.filter((timer) => timer.live).length, 1, 'the pause restarts on each keystroke');
  assert.equal(timers[timers.length - 1].ms, 1500);
  assert.equal(calls.length, 1, 'nothing is sent while typing');
  await fire();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].draft, 'Hel');
  assert.ok(calls.every((call) => call.ai === false));
  assert.equal(controller.state.ai.left, 17);
  assert.equal(controller.state.facts.length, 1);
});

test('an unchanged draft does not ask again', async () => {
  const { controller, calls, timers } = harness();
  await controller.start(ctx('same'));
  controller.update(ctx('same'));
  assert.equal(timers.length, 0);
  assert.equal(calls.length, 1);
});

test('AI ideas are requested only by askAi, once per click', async () => {
  const { controller, calls, fire } = harness({
    facts: { suggestions: [{ kind: 'fact', source: 'honor', title: 'A', detail: '' }], ai_left: 20 },
    ai: { source: 'ai', ai_left: 19, suggestions: [{ kind: 'fact', source: 'honor', title: 'A', detail: '' }, { kind: 'sentence', text: '[Student] led it.', source: 'honor', title: 'A' }] },
  });
  await controller.start(ctx('x'));
  controller.update(ctx('xy'));
  await fire();
  assert.equal(calls.filter((call) => call.ai).length, 0, 'typing and pauses never call AI');
  const first = controller.askAi();
  controller.askAi(); // a second click while loading is ignored
  await first;
  assert.equal(calls.filter((call) => call.ai).length, 1);
  assert.equal(controller.state.ai.left, 19);
  assert.equal(aiIdeasOf(controller.state.ai.items).length, 1);
  await controller.askAi();
  assert.equal(calls.filter((call) => call.ai).length, 2);
});

test('AI off or failing is reported without breaking the facts', async () => {
  const off = harness({ facts: { suggestions: [], ai_available: false } });
  await off.controller.start(ctx(''));
  assert.equal(off.controller.state.ai.available, false);
  await off.controller.askAi();
  assert.equal(off.calls.filter((call) => call.ai).length, 0, 'no button, no call');

  const failing = harness((payload) => { if (payload.ai) throw Object.assign(new Error('Busy'), { status: 429 }); return { suggestions: [{ kind: 'fact', title: 'T' }] }; });
  await failing.controller.start(ctx('a'));
  await failing.controller.askAi();
  assert.equal(failing.controller.state.ai.error, 'Busy');
  assert.equal(failing.controller.state.ai.available, true);
  assert.equal(failing.controller.state.facts.length, 1);

  const plain = harness({ facts: { suggestions: [] }, ai: { source: 'local', suggestions: [] } });
  await plain.controller.start(ctx('a'));
  await plain.controller.askAi();
  assert.equal(plain.controller.state.ai.unavailable, true);
});

test('a disposed controller stays quiet', async () => {
  const states = [];
  const calls = [];
  const controller = createIdeasController({ load: async (p) => { calls.push(p); return { suggestions: [] }; }, onChange: (s) => states.push(s), schedule: (fn) => fn, cancel() {} });
  controller.dispose();
  await controller.start(ctx('a'));
  assert.equal(states.length, 0);
});

// --- Check: shared Essay Coach rules with the letter criteria ---------------------------------
test('a letter check uses the five letter criteria', () => {
  assert.deepEqual(LETTER_KEYS, ['evidence', 'insight', 'context', 'structure', 'voice']);
  const model = normalizeLetterCheck({ result: { version: 2, scored: true, overall: 64, scores: { evidence: 3 }, notes: [
    { id: 'n1', criterion: 'context', question: 'Compared with whom?', context: 'Add a number.', priority: true },
    { id: 'n2', criterion: 'reflection', question: 'Odd key falls back' },
  ] } });
  assert.equal(model.scored, true);
  assert.equal(model.notes[0].criterion, 'context');
  assert.equal(model.notes[0].priority, true);
  assert.equal(model.notes[1].criterion, 'evidence');
  assert.equal(model.notes[0].quote, '', 'letter notes carry a question, not a quoted sentence');
});

test('Check again: blocked while notes are open or the text is unchanged, free once changed', () => {
  const notes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const anchored = new Set(['a', 'b']);
  let states = {};
  assert.equal(openNotes(notes, states, anchored).length, 2, 'a note whose sentence is gone does not count');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 2, changed: true }), 'notes_open');
  states = applyNoteState(applyNoteState(states, 'a', 'done'), 'b', 'dismissed');
  assert.equal(openNotes(notes, states, anchored).length, 0);
  assert.equal(doneNotes(notes, states).length, 2);
  assert.equal(goneNotes(notes, states, anchored).map((note) => note.id)[0], 'c');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 0, changed: false }), 'unchanged');
  assert.equal(recheckBlock({ hasCheck: true, openCount: 0, changed: true }), null);
  assert.equal(recheckBlock({ hasCheck: true, openCount: 3, changed: false, inputChanged: true }), null, 'a changed recommender detail is checked without the note rules');
  assert.equal(recheckBlock({ hasCheck: false, openCount: 0, changed: false }), null);
});

test('notes whose sentence vanished are marked gone, and reopened when it returns', () => {
  const notes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const updates = noteStateUpdates(notes, { b: 'gone', c: 'done' }, new Set(['a', 'b']));
  assert.deepEqual(updates, [{ id: 'b', state: 'open' }]);
  assert.deepEqual(noteStateUpdates(notes, {}, new Set(['a'])), [{ id: 'b', state: 'gone' }, { id: 'c', state: 'gone' }]);
  assert.deepEqual(noteStateUpdates(notes, { a: 'done' }, new Set(['a', 'b', 'c'])), []);
});

// --- routing -----------------------------------------------------------------------------------
test('letter workspace routes round-trip and stay inside the students page', () => {
  assert.deepEqual(parsePath('/students/15/letters/new'), { page: 'students', params: { studentId: 15, letterId: 'new' } });
  assert.deepEqual(parsePath('/students/15/letters/8/'), { page: 'students', params: { studentId: 15, letterId: 8 } });
  assert.equal(buildPath({ page: 'students', params: { studentId: 15, letterId: 'new' } }), '/students/15/letters/new');
  assert.equal(buildPath({ page: 'students', params: { studentId: 15, letterId: 8 } }), '/students/15/letters/8');
  assert.equal(buildPath({ page: 'students', params: { studentId: 15 } }), '/students/15');
  assert.equal(buildPath({ page: 'students', params: { letterId: 8 } }), '/students');
  for (const bad of ['/students/15/letters', '/students/15/letters/0', '/students/15/letters/x', '/students/0/letters/new', '/students/15/letters/8/9', '/students/15/essays/8']) {
    assert.equal(parsePath(bad), null, bad);
  }
  const counselor = { id: 2, role: 'counselor' };
  assert.deepEqual(resolveRoute(parsePath('/students/15/letters/8'), counselor), { page: 'students', params: { studentId: 15, letterId: 8 } });
});

test('check text shows the first name instead of [Student]', () => {
  const model = normalizeLetterCheck({ result: { version: 2, scored: true, overall: 40, summary: '[Student] helps.', suggestions: ['Show [Student] leading.'], strengths: [{ id: 's1', text: '[Student] is kind.' }], notes: [{ id: 'n', criterion: 'voice', question: 'What did [Student] do?', context: 'About [Student].' }] } });
  const filled = fillCheckText(model, 'Ramazon');
  assert.equal(filled.summary, 'Ramazon helps.');
  assert.deepEqual(filled.suggestions, ['Show Ramazon leading.']);
  assert.equal(filled.strengths[0].text, 'Ramazon is kind.');
  assert.equal(filled.notes[0].question, 'What did Ramazon do?');
  assert.equal(filled.notes[0].context, 'About Ramazon.');
  assert.equal(fillCheckText(null, 'R'), null);
});

test('a tiny hit grows to its sentence; a longer one stays as is', () => {
  const text = 'He is calm. His team trusts him a lot. Thanks.';
  const tiny = locateNotes(text, [{ id: 't', quote: 'trusts him' }]).get('t');
  assert.equal(text.slice(tiny.from, tiny.to), 'His team trusts him a lot.');
  const long = locateNotes(text, [{ id: 'l', quote: 'team trusts him a' }]).get('l');
  assert.equal(text.slice(long.from, long.to), 'team trusts him a');
  const line = 'First para ends.\nCalm\nNext.';
  const word = sentenceAround(line, 17, 21);
  assert.equal(line.slice(word.from, word.to), 'Calm');
});

test('line endings are normalized and a conflict is a coded error', () => {
  assert.equal(normalizeNewlines('a\r\nb\rc\n'), 'a\nb\nc\n');
  assert.equal(normalizeNewlines(null), '');
  assert.equal(conflictError('x').details.code, 'conflict');
});

test('a provider failure (503) on AI ideas keeps the button; 403 turns AI off', async () => {
  const busy = harness((payload) => { if (payload.ai) throw Object.assign(new Error('Unavailable'), { status: 503 }); return { suggestions: [] }; });
  await busy.controller.start(ctx('a'));
  await busy.controller.askAi();
  assert.equal(busy.controller.state.ai.available, true);
  const off = harness((payload) => { if (payload.ai) throw Object.assign(new Error('No'), { status: 403 }); return { suggestions: [] }; });
  await off.controller.start(ctx('a'));
  await off.controller.askAi();
  assert.equal(off.controller.state.ai.available, false);
});
