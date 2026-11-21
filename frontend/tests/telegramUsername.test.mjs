import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeTelegramUsername, telegramUsernameProblem } from '../src/lib/telegramUsername.js';

test('normalizes like the server: no @, no spaces, lowercase', () => {
  assert.equal(normalizeTelegramUsername('  @Dilnoza_K '), 'dilnoza_k');
  assert.equal(normalizeTelegramUsername(null), '');
  assert.equal(normalizeTelegramUsername('@'), '');
});

test('accepts 5-32 characters of a-z, 0-9 and _', () => {
  for (const value of ['abcde', '@Abc_123', 'a'.repeat(32), '', '   ']) assert.equal(telegramUsernameProblem(value), '', value);
});

test('says which rule is broken', () => {
  assert.equal(telegramUsernameProblem('abcd'), 'short');
  assert.equal(telegramUsernameProblem('a'.repeat(33)), 'long');
  for (const value of ['has space', 'dash-name', 'юзернейм', 'name!']) assert.equal(telegramUsernameProblem(value), 'characters', value);
});
