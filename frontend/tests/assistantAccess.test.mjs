import test from 'node:test';
import assert from 'node:assert/strict';
import { canUseAssistant, isAssistantSwitchedOff } from '../src/lib/assistantAccess.js';

test('the assistant shows only when /me/ allows it for a student or counselor', () => {
  assert.equal(canUseAssistant({ role: 'student', assistant_enabled: true }), true);
  assert.equal(canUseAssistant({ role: 'counselor', assistant_enabled: true }), true);
  assert.equal(canUseAssistant({ role: 'student', assistant_enabled: false }), false);
  assert.equal(canUseAssistant({ role: 'student' }), false, 'a user cached before the flag existed');
  for (const role of ['parent', 'teacher', 'organization', 'admin']) {
    assert.equal(canUseAssistant({ role, assistant_enabled: true }), false, role);
  }
  assert.equal(canUseAssistant(null), false);
});

test('only the switched-off 503 hides the assistant; a busy 503 does not', () => {
  assert.equal(isAssistantSwitchedOff({ status: 503, details: { code: 'assistant_disabled' } }), true);
  assert.equal(isAssistantSwitchedOff({ status: 503, details: { detail: 'The assistant is busy right now.' } }), false);
  assert.equal(isAssistantSwitchedOff({ status: 429, details: { code: 'assistant_disabled' } }), false);
  assert.equal(isAssistantSwitchedOff(new Error('offline')), false);
});
