import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildAssistantPayload, assistantSuggestions, MAX_MESSAGE_LENGTH } from '../src/lib/assistantChat.js';
import { assistantSource } from '../src/lib/assistantSource.js';
import { UI_TRANSLATIONS } from '../src/translations/ui.js';

test('payload carries the language and only the last 4 chat messages', () => {
  const messages = [{ id: 'w', role: 'assistant', local: true, content: 'welcome' }];
  for (let i = 0; i < 7; i += 1) messages.push({ id: `m${i}`, role: i % 2 ? 'assistant' : 'user', content: `text ${i}`, source: { key: 'local' } });
  messages.push({ id: 'empty', role: 'assistant', content: '' });
  const payload = buildAssistantPayload(messages, 'uz');
  assert.deepEqual(Object.keys(payload).sort(), ['language', 'messages']);
  assert.equal(payload.language, 'uz');
  assert.deepEqual(payload.messages.map((m) => m.content), ['text 3', 'text 4', 'text 5', 'text 6']);
  for (const message of payload.messages) assert.deepEqual(Object.keys(message).sort(), ['content', 'role']);
});

test('the message limit is 2000 characters', () => {
  assert.equal(MAX_MESSAGE_LENGTH, 2000);
});

test('chat text never touches browser storage', () => {
  for (const file of ['../src/components/AssistantCenter.jsx', '../src/lib/assistantChat.js']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB/i, file);
  }
});

test('every suggested question is translated into uz and ru', () => {
  for (const role of ['student', 'counselor']) {
    const list = assistantSuggestions(role);
    assert.ok(list.length >= 3);
    for (const question of list) {
      const entry = UI_TRANSLATIONS[question];
      assert.ok(entry && entry[0] && entry[1], `missing translation: ${question}`);
    }
  }
  assert.ok(assistantSuggestions('student').includes('What’s my next deadline?'));
  assert.ok(assistantSuggestions('counselor').includes('How many students are at risk?'));
  assert.ok(UI_TRANSLATIONS[assistantSource('budget-exhausted').note]);
});

test('instant and cached answers show no source note; budget note is calm', () => {
  for (const key of ['local', 'cache', 'gateway']) assert.equal(assistantSource(key).note, '');
  assert.match(assistantSource('budget-exhausted').note, /paused until tomorrow/);
});
