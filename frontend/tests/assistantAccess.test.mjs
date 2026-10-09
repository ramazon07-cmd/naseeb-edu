import test from 'node:test';
import assert from 'node:assert/strict';
import { assistantFailureReason, canUseAssistant, failedSend } from '../src/lib/assistantAccess.js';

test('the assistant shows exactly when /me/ says it is available', () => {
  assert.equal(canUseAssistant({ role: 'student', assistant_enabled: true }), true);
  assert.equal(canUseAssistant({ role: 'counselor', assistant_enabled: false }), false);
  assert.equal(canUseAssistant({ role: 'student' }), false, 'a user cached before the flag existed');
  assert.equal(canUseAssistant(null), false);
});

test('failures are told apart by status and code', () => {
  assert.equal(assistantFailureReason({ status: 503, details: { code: 'assistant_disabled' } }), 'switched_off');
  assert.equal(assistantFailureReason({ status: 403, details: { code: 'feature_not_in_plan' } }), 'not_in_plan');
  assert.equal(assistantFailureReason({ status: 503, details: { detail: 'The assistant is busy right now.' } }), 'busy');
  assert.equal(assistantFailureReason({ status: 429, details: {} }), 'limit');
  assert.equal(assistantFailureReason(new Error('offline')), 'connection');
});

test('a failed send drops the empty reply and leaves the composer usable', () => {
  const messages = [{ id: 'welcome' }, { id: 'user-1', content: 'Hi' }, { id: 'assistant-1', content: '' }];
  for (const reason of ['switched_off', 'not_in_plan']) {
    const next = failedSend(messages, 'assistant-1', reason);
    assert.deepEqual(next.messages.map((message) => message.id), ['welcome', 'user-1'], reason);
    assert.equal(next.status, 'ready', reason);
    assert.equal(next.unavailable, true, reason);
  }
  for (const reason of ['busy', 'limit', 'connection']) {
    const next = failedSend(messages, 'assistant-1', reason);
    assert.deepEqual(next.messages.map((message) => message.id), ['welcome', 'user-1'], reason);
    assert.equal(next.status, 'error', reason);
    assert.equal(next.unavailable, false, reason);
  }
});
